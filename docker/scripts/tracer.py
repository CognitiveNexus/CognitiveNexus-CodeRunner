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
        self.stepCounter = 0
        self.endState = 'finished'

    def invoke(self, arg, fromTty):
        print('== 开始执行 ==')
        threading.Thread(target=self._timeoutTask, daemon=True).start()
        gdb.execute('set pagination off')
        gdb.execute('set disable-randomization off')
        gdb.execute('file /sandbox/program')
        gdb.execute('rbreak code.c:.*')
        gdb.events.stop.connect(self._handleStop)
        gdb.events.exited.connect(self._finalize)
        gdb.execute('run < /sandbox/stdin > /sandbox/stdout 2>&1')

    def _handleStop(self, event):
        if isinstance(event, gdb.SignalEvent):
            if self.endState == 'finished':
                self.endState = 'aborted'
            return
        frame = gdb.selected_frame()
        sal = frame.find_sal()
        if sal.symtab.filename == '/sandbox/code.c':
            self._captureState()
        if self.stepCounter >= 500:
            print('== 步数超限 ==')
            self.endState = 'overstep'
            gdb.execute('interrupt')
            return
        gdb.execute('next')

    def _captureState(self):
        self.stepCounter += 1
        frame = gdb.selected_frame()

        with open('/sandbox/stdout', 'r') as f:
            stdout = f.read()

        stepData = OrderedDict([
            ('step', self.stepCounter),
            ('line', frame.find_sal().line),
            ('stdout', stdout),
            ('variables', OrderedDict()),
            ('memory', OrderedDict())
        ])

        block = frame.block()
        while block:
            for symbol in block:
                if symbol.is_variable:
                    self._processSymbol(symbol.name, stepData)
            block = block.superblock

        self.steps.append(stepData)

    def _processSymbol(self, varName, stepData):
        try:
            var = gdb.parse_and_eval(varName)
            varAddr = self._getAddress(var)
            stepData['variables'][varName] = varAddr
            if varAddr != 'N/A':
                self._parseValue(var, stepData['memory'], varAddr)
        except gdb.error:
            pass

    def _parseValue(self, value, memoryDict, baseAddr):
        try:
            ty = value.type.strip_typedefs()
            code = ty.code

            if code == gdb.TYPE_CODE_PTR:
                self._parsePointer(value, ty, baseAddr, memoryDict)
            elif code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
                self._parseStruct(value, ty, baseAddr, memoryDict)
            else:
                self._parsePrimitive(value, ty, baseAddr, memoryDict)
        except Exception as e:
            pass

    def _parsePointer(self, value, ptrType, ptrAddr, memoryDict):
        ptrVal = int(value)
        entry = OrderedDict()

        targetType = ptrType.target().strip_typedefs()
        entry['type'] = f'{targetType} *'
        entry['value'] = hex(ptrVal) if ptrVal != 0 else 'NULL'
        memoryDict[ptrAddr] = entry

        if ptrVal != 0:
            try:
                deref = value.dereference()
                self._parseValue(deref, memoryDict, hex(ptrVal))
            except (gdb.MemoryError, gdb.error):
                pass

    def _parseStruct(self, value, structType, baseAddr, memoryDict):
        typeName = str(structType)

        if typeName not in self.struct:
            offsets = OrderedDict()
            for field in structType.fields():
                if field.artificial or not field.name:
                    continue
                byteOffset = field.bitpos // 8
                offsets[field.name] = byteOffset
            self.struct[typeName] = offsets

        baseAddrInt = int(baseAddr, 16)
        for fieldName, offset in self.struct[typeName].items():
            fieldAddr = hex(baseAddrInt + offset)
            try:
                fieldVal = value[fieldName]
                self._parseValue(fieldVal, memoryDict, fieldAddr)
            except gdb.error as e:
                memoryDict[fieldAddr] = {'type': 'unknown', 'value': None}

    def _parsePrimitive(self, value, ty, addr, memoryDict):
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
        memoryDict[addr] = entry

    def _getAddress(self, value):
        try:
            return hex(int(value.address))
        except (gdb.error, ValueError, TypeError):
            return 'N/A'

    def _finalize(self, event):
        output = OrderedDict()
        output['struct'] = self.struct
        output['steps'] = self.steps
        output['endState'] = self.endState

        with open('/sandbox/dump.json', 'w') as f:
            json.dump(output, f, indent=2)

        print('== 执行完成 ==')
        print(f'已生成结果，共计 {self.stepCounter} 个步骤')

    def _timeoutTask(self):
        time.sleep(5)
        print('== 执行超时 ==')
        self.endState = 'timeout'
        gdb.execute('interrupt')

VariableTracker()