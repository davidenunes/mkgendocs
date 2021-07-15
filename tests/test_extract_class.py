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
