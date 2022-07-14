from mkgendocs.parse import Extract
from io import StringIO


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
