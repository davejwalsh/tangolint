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