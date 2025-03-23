import gdb
import json
import time
import uuid


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
        super().__init__('runTrace', gdb.COMMAND_USER)
        self.steps = []
        self.type_definitions = {}
        self.step_counter = 0
        self.end_state = 'finished'
        self.types = self.LinearDict()

    def invoke(self, arg, from_tty):
        print('== 开始执行 ==')
        gdb.Thread(target=self._timeout_task, daemon=True).start()
        gdb.execute('set pagination off')
        gdb.execute('set disable-randomization off')
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

        with open('/sandbox/stdout', 'r') as f:
            stdout = f.read()

        step_data = {
            'step': self.step_counter,
            'line': frame.find_sal().line,
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
            if var_addr != 'N/A':
                self._parse_value(val, step_data['memory'], var_addr)
        except gdb.error:
            pass

    def _parse_value(self, value: gdb.Value, memory_dict: dict, base_addr: str):
        try:
            ty = value.type.strip_typedefs()
            code = ty.code

            if code == gdb.TYPE_CODE_PTR:
                self._parse_pointer(value, ty, base_addr, memory_dict)
            elif code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
                self._parse_struct(value, ty, base_addr, memory_dict)
            else:
                self._parse_primitive(value, ty, base_addr, memory_dict)
        except Exception as e:
            pass

    def _parse_pointer(self, value: gdb.Value, ptr_type: gdb.Type, ptr_addr: str, memory_dict: dict):
        ptr_val = int(value)
        type_id = self._get_type_id(ptr_type)
        memory_dict[ptr_addr] = {
            'typeId': type_id,
            'rawBytes': hex(ptr_val)
        }

        if ptr_val != 0:
            try:
                deref = value.dereference()
                self._parse_value(deref, memory_dict, hex(ptr_val))
            except (gdb.MemoryError, gdb.error):
                pass

    def _parse_struct(self, value: gdb.Value, struct_type:gdb.Type, base_addr: str, memory_dict:dict):
        base_addr_int = int(base_addr, 16)
        for field in struct_type.fields():
            if not field.name:
                continue
            field_addr = hex(base_addr_int + (field.bitpos // 8))
            try:
                field_val = value[field.name]
                self._parse_value(field_val, memory_dict, field_addr)
            except gdb.error as e:
                memory_dict[field_addr] = { 'typeId': 'unknown', 'rawBytes': None }

    def _parse_primitive(self, value: gdb.Value, ty:gdb.Type, addr:str, memory_dict: dict):
        entry = {
            'typeId': self._get_type_id(ty)
        }
        try:
            if ty.code == gdb.TYPE_CODE_STRING:
                entry['rawBytes'] = value.string()
            elif ty.code == gdb.TYPE_CODE_FLT:
                entry['rawBytes'] = str(float(value))
            else:
                entry['rawBytes'] = str(int(value))
        except gdb.error:
            entry['rawBytes'] = str(value)
        memory_dict[addr] = entry

    def _get_address(self, value: gdb.Value):
        try:
            return hex(int(value.address))
        except (gdb.error, ValueError, TypeError):
            return 'N/A'

    def _get_type_id(self, ty: gdb.Type):
        if (type_id := self.types[ty]) is not None:
            return type_id

        base = ty.code
        if base == gdb.TYPE_CODE_PTR:
            target_type_id = self._get_type_id(ty.target().strip_typedefs())
            type_id = ty.name or f'{target_type_id}*'
            self.types[ty] = type_id
            type_definition = {
                'base': 'pointer',
                'name': ty.name,
                'size': ty.sizeof,
                'targetTypeId': target_type_id,
            }
        elif base == gdb.TYPE_CODE_ARRAY:
            element_type_id = self._get_type_id(ty.target().strip_typedefs())
            type_id = f'{element_type_id}[{ty.length}]'
            self.types[ty] = type_id
            type_definition = {
                "base": "array",
                "elementTypeId": element_type_id,
                "count": ty.length,
                "size": ty.sizeof
            }
        elif base == gdb.TYPE_CODE_STRUCT:
            type_id = f'struct {ty.name or f'<anonymous {uuid.uuid4()}>'}'
            self.types[ty] = type_id
            fields = { field.name: { "typeId": self._get_type_id(field.type.strip_typedefs()), "offset": field.bitpos // 8 } for field in ty.fields() if field.name }
            type_definition = {
                "base": "struct",
                "name": ty.name,
                "fields": fields,
                "size": ty.sizeof
            }
        elif base == gdb.TYPE_CODE_UNION:
            type_id = f'union {ty.name or f'<anonymous {uuid.uuid4()}>'}'
            self.types[ty] = type_id
            variants = { field.name: { "typeId": self._get_type_id(field.type.strip_typedefs()), "suffix": f'#{i}' } for i, field in enumerate(ty.fields()) if field.name }
            type_definition = {
                "base": "union",
                "name": ty.name,
                "variants": variants,
                "size": ty.sizeof
            }
        elif base in (
            gdb.TYPE_CODE_ENUM,
            gdb.TYPE_CODE_FLAGS,
            gdb.TYPE_CODE_FUNC,
            gdb.TYPE_CODE_SET,
            gdb.TYPE_CODE_RANGE,
            gdb.TYPE_CODE_STRING,
        ):
            type_id = 'unsupported'
            type_definition = {
                'base': 'unsupported',
                'name': ty.name or f'unsupported <{uuid.uuid4()}>',
                'size': ty.sizeof
            }
            self.types[ty] = type_id
        else:
            type_id = ty.name
            type_definition = {
                "base": "atomic",
                "name": ty.name,
                "size": ty.sizeof
            }
            self.types[ty] = type_id
        self.type_definitions[type_id] = type_definition
        return type_id

    def _finalize(self, event: gdb.Event):
        output = {
            'steps': self.steps,
            'typeDefinitions': self.type_definitions,
            'endState': self.end_state,
        }

        with open('/sandbox/dump.json', 'w') as f:
            json.dump(output, f, indent=2)

        print('== 执行完成 ==')
        print(f'已生成结果，共计 {self.step_counter} 个步骤')

    def _timeout_task(self):
        time.sleep(5)
        print('== 执行超时 ==')
        self.end_state = 'timeout'
        gdb.interrupt()

VariableTracer()