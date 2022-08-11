from mkgendocs.parse import Extract
from io import StringIO
import textwrap


def test_class_no_init():
    source_a = """class Test:\n
    \tdef __init__(self,a):\n
    \t\tself.a = a
    """
    source_b = """class Test:\n
    \ta = 3    
    """

    with StringIO(source_a) as source:
        extract = Extract(source)
        c = extract.get_class("Test")
        assert c["signature"] == "Test(\n   a\n)"

    with StringIO(source_b) as source:
        extract = Extract(source)
        c = extract.get_class("Test")
        assert c["signature"] == "Test()"


def test_async_function():
    """
        If the function is async it should be detected
        just like other function definitions

        #TODO this should probably be reflected in the signature
    """

    source = """async def a_func() -> bool:
    \"\"\" A Test Func
    \tReturns:
    \t\tbool: Returns True always
    \"\"\"
    return True\n
    """

    with StringIO(source) as source:
        extract = Extract(source)
        c = extract.get_function("a_func")
        assert c["signature"] == "a_func()"


def test_abstract_method():
    source = """
    from abc import ABC, abstractmethod
    
    class Sample1(ABC):
        '''
        Sample class 1
        '''
        @abstractmethod
        def sample_method_abstract(self):
            '''
            sample abstract
            '''
            pass
            
        def sample_method_implement(self):
            '''
            sample implement 1
            '''
            pass
            
            
    class Sample2(Sample1):
        '''
        Sample class 2
        '''
        def sample_method_implement(self):
            '''
            sample implement 2
            '''
            pass
            
    """
    source = textwrap.dedent(source)
    with StringIO(source) as source:
        extract = Extract(source)
        m = extract.get_method("Sample1", "sample_method_abstract")
        assert m["signature"] == "sample_method_abstract()"

        class_methods = extract.get_methods("Sample1")
        assert len(class_methods) == 2
