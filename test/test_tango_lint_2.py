import time
import threading
from tango import AttrWriteType
from tango.server import Device, attribute, command, device_property


# T040, T041: no default_value or doc
# T033: init_device doesn't call super
# T034: delete_device doesn't call super
# T035: always_executed_hook doesn't call super
# T042: (no missing init_device here since it's defined)
# T043: __del__ used instead of delete_device
# T046: time.sleep in device method
# T047: threading.Thread in device method
class badDevice(Device):
    
    Host: str = device_property(dtype=str)  # T040, T041

    Port: int = device_property(dtype=int, default_value=8080)  # T041 only

    def init_device(self):  # T033: no super().init_device()
        self._value = 0

    def delete_device(self):  # T034: no super().delete_device()
        self._value = None

    def always_executed_hook(self):  # T035: no super call
        pass


    def __del__(self):  # T043: use delete_device instead
        self._value = None

    def some_method(self):
        time.sleep(2)  # T046: blocks event loop
        self._t = threading.Thread(target=self.some_method)  # T047

    # T044: no label
    # T045: READ_WRITE but no write_voltage method
    @attribute(dtype=float, description="Output voltage", unit="V", access=AttrWriteType.READ_WRITE)
    def voltage(self) -> float:
        return 3.3

    # T049: has param but no dtype_in, has return but no dtype_out
    @command
    def SetTarget(self, value: float) -> float:
        return value


# T042: no init_device defined at all
class MinimalDevice(Device):
    pass
