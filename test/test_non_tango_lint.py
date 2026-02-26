import numpy as np  # F401 (ruff)

class MyClass:
    def method_one(self) -> int:
        return "Hello"
    def method_two(self) -> None:
        pring("World") 

    def add(self, x: int, y: int) -> int:
        return x + y

def takes_int(x: int) -> None:
    pass


value: int = "not an int" 

takes_int("wrong type") 

obj = MyClass()
obj.non_existent_method()


import numpy as np  # F401 (unused import)
import os  # F401 (unused import)


class MyClass:
    def method_one(self) -> int:
        return "Hello"  # mypy: incompatible return type

    def method_two(self) -> None:
        pring("World")  # F821 undefined name (typo)

    def add(self, x: int, y: int) -> int:
        unused_var = 123  # F841 unused variable
        return x + y


def takes_int(x: int) -> None:
    pass


value: int = "not an int"  # mypy: incompatible assignment

takes_int("wrong type")  # mypy: wrong argument type

obj = MyClass()
obj.non_existent_method()  # mypy: attribute does not exist


# Ruff-specific issues below

x = None
if x == None:  # E711 comparison to None should be "is None"
    pass

very_long_variable_name = "This is an extremely long string that will definitely exceed the typical 88 character limit used by Ruff and Black for Python formatting compliance"  # E501 line too long

42  # B018 useless expression

def badFormatting():
    return 1
def anotherBadFormatting():
    return 2  # E302 expected 2 blank lines between top-level functions