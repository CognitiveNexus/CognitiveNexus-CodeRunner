import gdb
import json
import time
import threading
from collections import OrderedDict

class VariableTracker(gdb.Command):
    def __init__(self):
        super().__init__('runTrace', gdb.COMMAND_USER)
        self.steps = []
        self.struct = OrderedDict()
        self.step_counter = 0
        self.end_state = 'finished'

    def invoke(self, arg, from_tty):
        print('== 开始执行 ==')
        threading.Thread(target=self._timeout_task, daemon=True).start()
        gdb.execute('set pagination off')
        gdb.execute('set disable-randomization off')
        gdb.execute('file /sandbox/program')
        gdb.execute('rbreak code.c:.*')
        gdb.events.stop.connect(self._handle_stop)
        gdb.events.exited.connect(self._finalize)
        gdb.execute('run < /sandbox/stdin > /sandbox/stdout 2>&1')

    def _handle_stop(self, event):
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

        step_data = OrderedDict([
            ('step', self.step_counter),
            ('line', frame.find_sal().line),
            ('stdout', stdout),
            ('variables', OrderedDict()),
            ('memory', OrderedDict())
        ])

        block = frame.block()
        while block:
            for symbol in block:
                if symbol.is_variable:
                    self._process_symbol(symbol.name, step_data)
            block = block.superblock

        self.steps.append(step_data)

    def _process_symbol(self, var_name, step_data):
        try:
            var = gdb.parse_and_eval(var_name)
            var_addr = self._get_address(var)
            step_data['variables'][var_name] = var_addr
            if var_addr != 'N/A':
                self._parse_value(var, step_data['memory'], var_addr)
        except gdb.error:
            pass

    def _parse_value(self, value, memory_dict, base_addr):
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

    def _parse_pointer(self, value, ptr_type, ptr_addr, memory_dict):
        ptr_val = int(value)
        entry = OrderedDict()

        target_type = ptr_type.target().strip_typedefs()
        entry['type'] = f'{target_type} *'
        entry['value'] = hex(ptr_val) if ptr_val != 0 else 'NULL'
        memory_dict[ptr_addr] = entry

        if ptr_val != 0:
            try:
                deref = value.dereference()
                self._parse_value(deref, memory_dict, hex(ptr_val))
            except (gdb.MemoryError, gdb.error):
                pass

    def _parse_struct(self, value, struct_type, base_addr, memory_dict):
        type_name = str(struct_type)

        if type_name not in self.struct:
            offsets = OrderedDict()
            for field in struct_type.fields():
                if field.artificial or not field.name:
                    continue
                byte_offset = field.bitpos // 8
                offsets[field.name] = byte_offset
            self.struct[type_name] = offsets

        base_addr_int = int(base_addr, 16)
        for field_name, offset in self.struct[type_name].items():
            field_addr = hex(base_addr_int + offset)
            try:
                field_val = value[field_name]
                self._parse_value(field_val, memory_dict, field_addr)
            except gdb.error as e:
                memory_dict[field_addr] = {'type': 'unknown', 'value': None}

    def _parse_primitive(self, value, ty, addr, memory_dict):
        entry = OrderedDict()
        entry['type'] = str(ty)
        try:
            if ty.code == gdb.TYPE_CODE_STRING:
                entry['value'] = value.string()
            elif ty.code == gdb.TYPE_CODE_FLT:
                entry['value'] = float(value)
            else:
                entry['value'] = int(value)
        except gdb.error:
            entry['value'] = str(value)
        memory_dict[addr] = entry

    def _get_address(self, value):
        try:
            return hex(int(value.address))
        except (gdb.error, ValueError, TypeError):
            return 'N/A'

    def _finalize(self, event):
        output = OrderedDict()
        output['struct'] = self.struct
        output['steps'] = self.steps
        output['endState'] = self.end_state

        with open('/sandbox/dump.json', 'w') as f:
            json.dump(output, f, indent=2)

        print('== 执行完成 ==')
        print(f'已生成结果，共计 {self.step_counter} 个步骤')

    def _timeout_task(self):
        time.sleep(5)
        print('== 执行超时 ==')
        self.end_state = 'timeout'
        gdb.execute('interrupt')

VariableTracker()