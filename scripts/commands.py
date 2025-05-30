import gdb
import json
import time
import threading

class VariableTracer(gdb.Command):
    class LinearDict:
        def __init__(self):
            self._keys = []
            self._values = []

        def __setitem__(self, key, value):
            for i, k in enumerate(self._keys):
                if k == key:
                    self._values[i] = value
                    return
            self._keys.append(key)
            self._values.append(value)

        def __getitem__(self, key):
            for i, k in enumerate(self._keys):
                if k == key:
                    return self._values[i]
            return None

    def __init__(self):
        super().__init__('tracer', gdb.COMMAND_USER)
        self.steps = []
        self.type_definitions = {}
        self.step_counter = 0
        self.end_state = 'finished'
        self.types = self.LinearDict()
        self.previous_line = None
        self.anonymous_counter = 0

    def invoke(self, arg, from_tty):
        print('== 开始执行 ==')
        gdb.Thread(target=self._timeout_task, daemon=True).start()
        gdb.execute('file /sandbox/program')
        gdb.execute('rbreak code.c:.*')
        gdb.events.stop.connect(self._handle_stop)
        gdb.events.exited.connect(self._finalize)
        gdb.execute('run < /sandbox/stdin > /sandbox/stdout 2>&1')

    def _handle_stop(self, event: gdb.Event):
        if isinstance(event, gdb.SignalEvent):
            if self.end_state == 'finished':
                self.end_state = 'aborted'
            return
        frame = gdb.selected_frame()
        sal = frame.find_sal()
        if sal.symtab.filename == '/sandbox/code.c':
            self._capture_state()
        if self.step_counter >= 500:
            print('== 步数超限 ==')
            self.end_state = 'overstep'
            gdb.execute('interrupt')
            return
        gdb.execute('next')

    def _capture_state(self):
        self.step_counter += 1
        frame = gdb.selected_frame()
        current_line = frame.find_sal().line

        if self.previous_line is None:
            self.previous_line = current_line
            return

        with open('/sandbox/stdout', 'r') as f:
            stdout = f.read()

        step_data = {
            'step': self.step_counter,
            'line': self.previous_line,
            'stdout': stdout,
            'variables': [],
            'memory': {},
        }

        block = frame.block()
        while block:
            for symbol in block:
                if symbol.is_variable:
                    self._process_symbol(symbol.name, step_data)
            block = block.superblock

        self.steps.append(step_data)
        self.previous_line = current_line

    def _process_symbol(self, var_name: str, step_data: dict):
        try:
            val = gdb.selected_frame().read_var(var_name)
            var_addr = self._get_address(val)
            type_id = self._get_type_id(val.type)
            step_data['variables'].append({
                'name': var_name,
                'typeId': type_id,
                'address': var_addr,
            })
            if var_addr not in ('NULL', 'N/A'):
                self._parse_value(val, step_data['memory'], var_addr)
        except gdb.error:
            pass

    def _parse_value(self, value: gdb.Value, memory_dict: dict, base_addr: str):
        try:
            ty = value.type.strip_typedefs()
            code = ty.code

            if code == gdb.TYPE_CODE_PTR:
                self._parse_pointer(value, ty, base_addr, memory_dict)
            elif code == gdb.TYPE_CODE_ARRAY:
                self._parse_array(value, ty, base_addr, memory_dict)
            elif code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
                self._parse_composite(value, ty, base_addr, memory_dict)
            else:
                self._parse_primitive(value, ty, base_addr, memory_dict)
        except Exception as e:
            pass

    def _parse_pointer(self, value: gdb.Value, ptr_type: gdb.Type, ptr_addr: str, memory_dict: dict):
        ptr_val = int(value)
        type_id = self._get_type_id(ptr_type)
        
        memory_dict[f'{ptr_addr}:{type_id}'] = {
            'value': hex(ptr_val) if ptr_val else 'NULL',
            'rawBytes': self._get_raw_bytes(value),
        }

        if ptr_val != 0:
            try:
                self._parse_value(value.dereference(), memory_dict, hex(ptr_val))
            except (gdb.MemoryError, gdb.error):
                pass
    
    def _parse_array(self, value: gdb.Value, arr_type: gdb.Type, arr_addr: str, memory_dict: dict):
        base_address = int(arr_addr, 16)
        element_size = arr_type.target().strip_typedefs().sizeof
        array_length = arr_type.sizeof // element_size

        for i in range(array_length):
            try:
                element = value[i]
                element_addr = base_address + i * element_size
                self._parse_value(element, memory_dict, hex(element_addr))
            except (gdb.MemoryError, gdb.error, ValueError):
                pass

    def _parse_composite(self, value: gdb.Value, comp_type: gdb.Type, base_addr: str, memory_dict: dict):
        base_address = int(base_addr, 16)
        fields = []

        for field in comp_type.fields():
            fields.append({
                'base_offset': 0,
                'field': field,
            })

        while fields:
            base_offset, field = fields.pop(0).values()
            offset = field.bitpos // 8 if comp_type.code == gdb.TYPE_CODE_STRUCT else 0
            field_addr = hex(base_address + base_offset + offset)
            
            if field.name:
                self._parse_value(value[field.name], memory_dict, field_addr)
            else:
                for child_field in field.type.fields():
                    fields.append({
                        'base_offset': offset,
                        'field': child_field,
                    })

    def _parse_primitive(self, value: gdb.Value, ty:gdb.Type, addr:str, memory_dict: dict):
        type_id = self._get_type_id(ty)
        memory_dict[f'{addr}:{type_id}'] = {
            'value': value.format_string(),
            'rawBytes': self._get_raw_bytes(value),
        }

    def _get_address(self, value: gdb.Value):
        try:
            addr = int(value.address)
            return hex(addr) if addr else 'NULL'
        except (gdb.error, ValueError, TypeError):
            return 'N/A'

    def _get_raw_bytes(self, value: gdb.Value,):
        return ' '.join(f'{byte:02X}' for byte in value.bytes)

    def _get_type_id(self, ty: gdb.Type, save: bool = True):
        if (type_id := self.types[ty]) is not None:
            return type_id

        base = ty.code
        if base == gdb.TYPE_CODE_PTR:
            target_type_id = self._get_type_id(ty.target().strip_typedefs())
            type_id = ty.name or f'{target_type_id}*'
            self.types[ty] = type_id
            type_definition = {
                'base': 'pointer',
                'targetTypeId': target_type_id,
                'size': ty.sizeof,
            }
        elif base == gdb.TYPE_CODE_ARRAY:
            element_type = ty.target().strip_typedefs()
            element_type_id = self._get_type_id(element_type)
            length = ty.sizeof // element_type.sizeof
            type_id = f'{element_type_id}[{length}]'
            self.types[ty] = type_id
            type_definition = {
                'base': 'array',
                'elementTypeId': element_type_id,
                'length': length,
                'size': ty.sizeof,
            }
        elif base in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
            base_name = 'struct' if base == gdb.TYPE_CODE_STRUCT else 'union'
            type_id = f'{base_name} {ty.name or f'<anonymous {self._get_anonymous_id()}>'}'
            self.types[ty] = type_id
            fields = {}
            for field in ty.fields():
                offset = (field.bitpos // 8) if base_name == 'struct' else 0
                if field.name:
                    fields[field.name] = {
                        'typeId': self._get_type_id(field.type.strip_typedefs()),
                        'offset': offset
                    }
                else:
                    child_struct = self._get_type_id(field.type.strip_typedefs(), False)
                    for field_name, field_detail in child_struct['fields'].items():
                        fields[field_name] = {
                            'typeId': field_detail['typeId'],
                            'offset': offset + field_detail['offset']
                        }
            type_definition = {
                'base': base_name,
                'fields': fields,
                'size': ty.sizeof
            }
        elif base in (
            gdb.TYPE_CODE_ENUM,
            gdb.TYPE_CODE_FLAGS,
            gdb.TYPE_CODE_FUNC,
            gdb.TYPE_CODE_SET,
            gdb.TYPE_CODE_RANGE,
            gdb.TYPE_CODE_STRING,
        ):
            type_id = f'unsupported {ty.name or f'<anonymous {self._get_anonymous_id()}>'}'
            type_definition = {
                'base': 'unsupported',
                'size': ty.sizeof,
            }
            self.types[ty] = type_id
        else:
            type_id = ty.name
            type_definition = {
                'base': 'atomic',
                'size': ty.sizeof,
            }
            self.types[ty] = type_id

        if save:
            self.type_definitions[type_id] = type_definition
            return type_id
        else:
            return type_definition
    
    def _get_anonymous_id(self):
        self.anonymous_counter += 1
        return self.anonymous_counter

    def _finalize(self, event: gdb.Event):
        output = {
            'steps': self.steps,
            'typeDefinitions': self.type_definitions,
            'endState': self.end_state,
        }

        with open('/sandbox/result.json', 'w') as f:
            json.dump(output, f, indent=2)

        print('== 执行完成 ==')
        print(f'已生成结果，共计 {self.step_counter} 个步骤')

    def _timeout_task(self):
        time.sleep(5)
        print('== 执行超时 ==')
        self.end_state = 'timeout'
        gdb.interrupt()

class CodeJudger(gdb.Command):
    def __init__(self):
        super().__init__('judger', gdb.COMMAND_USER)
        with open('/sandbox/tests.json', 'r') as f:
            self.tests = json.load(f)
        self.completed = 0
        self.inferiors = {}
        self.lock = threading.Lock()
    
    def invoke(self, arg, from_tty):
        print('== 开始执行 ==')
        gdb.events.exited.connect(self._finalize)
        for test_index, test in enumerate(self.tests):
            test['endState'] = 'finished'
            gdb.execute('add-inferior')
            inferior = gdb.inferiors()[-1]
            inferior_num = inferior.num
            self.inferiors[inferior_num] = {
                'inferior': inferior,
                'test_index': test_index,
                'finished': False
            }
            with open(f'/sandbox/stdin_{inferior_num}', 'w') as f:
                f.write(test['stdin'])

            gdb.execute(f'inferior {inferior_num}')
            gdb.execute('file /sandbox/program')
            gdb.execute(f'run < /sandbox/stdin_{inferior_num} > /sandbox/stdout_{inferior_num} 2>&1')
        with open('/sandbox/result.json', 'w') as f:
            json.dump({'tests': self.tests}, f, indent=2)
        print('== 全部完成 ==')

    def _finalize(self, event: gdb.Event):
        with self.lock:
            self.completed += 1
        inferior_num = event.inferior.num
        self.inferiors[inferior_num]['finished'] = True
        test = self.tests[self.inferiors[inferior_num]['test_index']]

        with open(f'/sandbox/stdout_{inferior_num}', 'r') as f:
            test['stdout'] = f.read()

gdb.execute('set pagination off')
gdb.execute('set disable-randomization off')
VariableTracer()
CodeJudger()