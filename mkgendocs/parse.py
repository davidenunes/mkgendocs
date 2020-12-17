"""
This module provides parsers for Google docstring format. The
parsers work on docstring data objects that are collected using the `Extract`
class. After parsing, the data of docstring is stored in a dictionary. This
data can for instance be serialized using JSON, or rendered to markdown.
"""
import re
import warnings
import ast
import astor


class DocString(object):
    """
    This is the base class for parsing docstrings.
    Default behavior of the parser can be modified by passing a dict called
    `config` during initialization. This dict does only have to contain the
    key-value pairs for the configuration settings to change. Possible options
    are listed and explained below.

    Attributes:
        delimiter: A string that is used to identify a section and is placed
            after the section name (e.g., `Arguments:`). Defaults to `': '`.
        arg_delimiter: A string that specifies how to separate arguments in a
            argument list. Defaults to `':'`.
        indent: An int that specifies the minimum number of spaces to use for
            indentation. Defaults to `4`.
        code: Convert code blocks to Markdown. Defaults to `'python'`. Use
            `None` to disable. Use `''` (empty string) to convert code blocks to
            markdown, but disable syntax highlighting.
        ignore_args_for_undefined_headers: A flag that if set to `True` treats
            argument lists as text if the header is unknown, or does not exist.
        check_args: A flag that if set to `True` checks if all arguments are
            documented in a docstring, and if their types are correct. For this
            option to work, the optional input `args` must be passed upon
            initialization.
        override_annotations: A flag that if set to `True` sets the argument
            annotation field in a docstring (optional) to the value specified by
            the optional input `args`.
        warn_if_no_arg_doc: Issue a warning if an argument does not have any
            documentation. For this option to work, `args` must be passed.
            Defaults to `True`.
        exclude_warn_if_no_arg_doc: Do no issue warnings for args missing
            documentation if they are part of this list. Defaults to `['self']`.
    """

    def __init__(self, docstring, signature=None, config=None):
        """
        Initialize a new parser.
        Args:
            signature(dict, optional): A dict containing arguments and return
                annotations. See the function `parse_signature' to construct
                this dict from a PEP484 annotated signature. When this argument
                is specified, the parser will assign types to arguments using
                this dict instead of obtaining them from the docstrings.
            config(dict, optional): A dict containing optional configuration
                settings that modify default behavior.
        """
        self.header = {}
        self.docstring = docstring if docstring is not None else ""
        self.data = []
        self.signature = signature

        default_config = {'delimiter': ':',
                          'arg_delimiter': ': ',
                          'indent': 4,
                          'check_args': True,
                          'override_annotations': True,
                          'warn_if_no_arg_doc': True,
                          'exclude_warn_if_no_arg_doc': ['self'],
                          'code': 'python',
                          'warn_if_undefined_header': True,
                          'ignore_args_for_undefined_headers': True,
                          'headers': '',
                          'blocks': '',
                          'extra_headers': '',
                          'args': '',
                          'returns': ''}

        self._config = get_config(default_config, config)

        # TODO tidy this up
        # Internals for parsing
        # section : This variable will hold the contents of each unparsed section
        # sections : A list that will hold all unparsed sections.
        # lieno : line number relative to the current section being parsed.
        # _re .. : Regex functions.
        # _indent : This variable will hold the current indentation (number of spaces).

        self._state = {
            'indent': 0,
            'lineno': 0,
            'sections': [],
            'section': []
        }
        self._re = {}

    def parse(self):
        """
        This method should be overridden to parse docstring sections
        """
        self.data = []
        self.extract_sections()
        for section in self._state['sections']:
            self.data.append(self.parse_section(section))

        for i, di in enumerate(self.data):
            self.check_args(di)
            if self.signature:
                self.override_annotations(self.data[i], self.signature['args'],
                                          self._config['args'].split('|'))
                self.override_annotations(
                    self.data[i], {'': self.signature['return_annotation']},
                    self._config['returns'].split('|'))
            self.mark_code_blocks(self.data[i])

        return self.data

    def extract_sections(self):
        """
        This method should be overloaded to specify how to extract sections.
        """
        pass

    def parse_section(self, section):
        """
        This method should be overloaded to specify how to parse a section.
        """
        pass

    def __json__(self):
        """
        Output docstring as JSON data.
        """
        import json

        data = self.data
        data.append(self.header)
        return json.dumps(
            self.data, sort_keys=True, indent=4, separators=(',', ': '))

    def __str__(self):
        """
        This method should be overloaded to specify how to output to plain-text.
        """
        return self.docstring

    def markdown(self):
        """
        Output data relevant data needed for markdown rendering.
        Args:
            filename (str, optional) : select template to use for markdown
                rendering.
        """
        data = self.data
        headers = self._config['headers'].split('|')
        return headers, data

    def check_args(self, section):
        """
        Check if all args have been documented in the docstring and if, they
        have annotations, annotations matches the ones in the function
        signature. This method only works when `signature` have been specified.
        """
        if not self.signature or not self._config['check_args']:
            return

        docstring_args = {}

        if section['header'] in self._config['args'].split('|'):
            for arg in section['args']:
                docstring_args[arg['field']] = arg

            for arg in self.signature['args']:
                # Skip checks if signature does not contain any annotations
                # or if the argument should not have documentation.
                if not self.signature['args'][arg] or \
                        arg in self._config['exclude_warn_if_no_arg_doc']:
                    continue
                if arg not in docstring_args and \
                        self._config['warn_if_no_arg_doc']:
                    warnings.warn(
                        'Missing documentation for `%s` in docstring.' % arg,
                        UserWarning)
                elif docstring_args[arg]['signature'] != \
                        '(%s)' % self.signature['args'][arg] and \
                        docstring_args[arg]['signature'] != '':
                    warnings.warn(
                        'Annotation mismatch for `%s` in docstring.' % arg,
                        UserWarning)
            for arg in docstring_args:
                if arg not in self.signature['args']:
                    warnings.warn(' Found argument `%s` in docstring that does' \
                                  ' not exist in function signature.' % arg, UserWarning)

    def override_annotations(self, section, parsed_args, headers):
        """
        Override argument annotations in docstrings with annotations found in
        `args`.
        """
        if not parsed_args or not self._config['override_annotations']:
            return

        if not section['header'] in headers:
            return

        args = section['args']
        section['args'] = []
        for arg in args:
            out = arg
            if arg['field'] in parsed_args and parsed_args[arg['field']]:
                out['signature'] = parsed_args[arg['field']]
            section['args'].append(out)

    def mark_code_blocks(self, section):
        """
        Enclose code blocks in formatting tags if option `config['code']` is
        not None.
        """
        if not self._config['code']:
            return

        section['text'] = mark_code_blocks(
            section['text'], lang=self._config['code'])


class GoogleDocString(DocString):
    """
    This is the base class for parsing docstrings that are formatted according
    to the Google style guide.
    Google docstrings are treated as sections that begin with a header (say,
    Args) and are then followed by either an argument list or some text.
    The headers are identified based on a keyword search.
    In addition to the configuration settings provided by the baseclass, the
    GoogleDocString class introduces some additional configurable parameters,
    listed and explained below.
    Attributes:
        headers: A string of header keywords, each separated by `|`.
        extra_headers: Modify this argument to include additional header
            keywords.
        args: A string that specifies the name of the `Args` section. This value
            is used to assign types to the argument list by passing the argument
            `args` upon initialization (see baseclass for further details).
        returns: A string that specifies the name of the `Returns` section. The
            use of this argument is the same as for `args`.

    """

    def __init__(self, docstring, signature=None, config=None):
        """
        Initialize GoogleDocString parser.
        """
        import os

        default_config = {}
        default_config['headers'] = \
            ('Args|Arguments|Returns|Yields|Raises|Note|Properties|Fields' +
             'Notes|Example|Examples|Attributes|Todo|References')
        default_config['blocks'] = 'note|seealso|abstract|summary|tldr|info|todo|tip|hint|important|success|check' \
                                   '|done|question|help|faq|warning|caution|attention|failure|fail|missing|danger' \
                                   '|error|bug|example|snippet|quote|cite '
        default_config['extra_headers'] = ''
        default_config['args'] = 'Args|Arguments'
        default_config['returns'] = 'Returns|'

        config = get_config(default_config, config, warn=0)

        if config['extra_headers']:
            config['headers'] += '|' + config['extra_headers']

        super(GoogleDocString, self).__init__(docstring, signature, config)

        self._re = {
            'header': self._compile_header(),
            'block': self._compile_block(),
            'indent': self._compile_indent(),
            'arg': self._compile_arg()
        }

    def parse_section(self, section):
        """
        Parses blocks in a section by searching for an argument list, and
        regular notes. The argument list must be the first block in the section.
        A section is broken up into multiple blocks by having empty lines.
        Returns:
            A dictionary that contains the key `args` for holding the argument
            list (`None`) if not found and the key `text` for holding regular
            notes.
        Example:
            ```
            Section:
                This is block 1 and may or not contain an argument list (see
                `args` for details).
                This is block 2 and any should not contain any argument list.
            ```
        """
        # Get header
        lines = section.split('\n')

        # escape mathjax
        # header = self._compile_header().findall(lines[0])

        # Skip the first line if it is a header
        header = self._get_header(lines[0])
        self._state['linenum'] = int(bool(header))
        text = []
        signature = None
        out = {}
        args = []
        while self._state['linenum'] < len(lines):
            arg_data = self._parse_arglist(lines)
            if self._state['linenum'] == 0:
                signature = self.get_signature(lines[0])
                if signature:
                    out["signature"] = signature

            if not header and arg_data and self._config['warn_if_undefined_header'] and not \
                    (self._state['linenum'] == 0 and signature is not None):
                # if it's not a header it's just text
                # warnings.warn(str(arg_data))
                # warnings.warn(str(self._state['linenum']))
                # warnings.warn("Undefined header: '%s'" % header + ' followed by an argument list.')
                # basically who created this parser did't do that good of a job with the regex for args
                # because anything with a delimiter is an arg
                # TODO re-write this later with state in mind, only gather args if the previous was an header
                pass
            if (arg_data and header) or (
                    arg_data and not header and not self._config['ignore_args_for_undefined_headers']):
                args.append(arg_data)
            else:
                if self._state['linenum'] > 0 or not signature:
                    text.append(lines[self._state['linenum']])
            self._state['linenum'] += 1

        out['header'] = header
        out['text'] = '\n'.join(text)
        out['args'] = args

        return out

    def get_signature(self, line: str, name=None):
        line = line.strip()
        name = name if name is not None else "\w*\_?\w*"
        signature_like = r'%s\((?:[^,]+\s*[,]\s*)*[^,]*\)' % name

        found = re.match(signature_like, line)

        return found.group() if found else None

    def extract_sections(self):
        """
        TODO when we have \n in args, it removes them from the result markdown
        Extracts sections from the docstring. Sections are identified by an
        additional header which is a recognized Keyword such as `Args` or
        `Returns`. All text within  a section is indented and the section ends
        after the indention.
        """

        lines = self.docstring.split('\n')
        new_section = True
        new_block = False

        for linenumber, line in enumerate(lines):
            # Compute amount of indentation
            current_indent = self._get_indent(line)

            # Capture indent to be able to remove it from the text and also
            # to determine when a section ends.
            # The indent is reset when a new section begins.
            if new_section and self._is_indent(line):
                self._state['indent'] = current_indent
                new_section = False

            if new_block and self._is_indent(line):
                new_block = False

            if self._is_header(line):
                self._err_if_missing_indent(lines, linenumber)
                self._end_section()
                self._begin_section()
                new_section = True
                new_block = False
            elif self._is_block(line):
                self._err_if_missing_indent(lines, linenumber)
                self._end_section()
                self._begin_section()
                new_block = True
                new_section = False
            # Section ends because of a change in indent that is not caused
            # by a line break
            elif line and current_indent < self._state['indent']:
                self._end_section()
                self._begin_section()

            self._state['section'].append(line[self._state['indent']:])

        self._end_section()
        self._begin_section()

    def _parse_arglist(self, lines, require=False):
        arg_data = self._get_arg(lines[self._state['linenum']])

        if not arg_data:
            if require:
                raise ValueError('Failed to parse argument list:\n `%s` ' %
                                 (self._state['section']))
            return None

        # Take into account that the description can be multi-line
        # the next line has to be indented
        description = [arg_data[0][2]]
        next_line = _get_next_line(lines, self._state['linenum'])
        while self._is_indent(next_line):
            self._state['linenum'] += 1
            description.append(lines[self._state['linenum']])
            next_line = _get_next_line(lines, self._state['linenum'])

        return {
            'field': arg_data[0][0],
            'signature': arg_data[0][1],
            'description': '\n'.join(description)
        }

    def _compile_header(self):
        return re.compile(r'^\s*(%s)%s\s*' % (self._config['headers'],
                                              self._config['delimiter']))
        # return re.compile(r'^\s*(%s)%s\s*\n' % (self._config['headers'],

    def _compile_block(self):
        return re.compile(r'^\s*(?:\!{3})|(?:\?{3}) (%s) (?:\".*\")?\s*' % self._config['blocks'])

    def _compile_indent(self):
        return re.compile(r'(^\s{%s,})' % self._config['indent'])

    def _compile_arg(self):
        return re.compile(
            r'(\w*)\s*(\(.*\))?\s*%s(.*)' % self._config['arg_delimiter'])

    def _err_if_missing_indent(self, lines, lineno):
        next_line = _get_next_line(lines, lineno)
        is_next_indent = self._is_indent(next_line)
        if not is_next_indent:
            err_msg = f"Invalid section: docstring line {lineno}: missing indent after \"{lines[lineno]}\" "
            raise SyntaxError(err_msg)

    def _begin_section(self):
        self._state['section'] = []
        self._state['indent'] = 0

    def _end_section(self):
        section_text = '\n'.join(self._state['section'])
        if section_text.strip():
            self._state['sections'].append(section_text)

    def _get_indent(self, line):
        """
        Returns the indentation size.
        """
        indent_size = self._re['indent'].findall(line)
        if indent_size:
            return len(indent_size[0])
        else:
            return 0

    def _is_indent(self, line):
        """
        Returns if the line is indented or not.
        """
        indent = self._get_indent(line)
        return bool(indent > 0)

    def _is_header(self, line):
        return bool(self._re['header'].findall(line))

    def _is_block(self, line):
        return bool(self._re['block'].findall(line))

    def _get_header(self, line):
        header = self._re['header'].findall(line)
        if header:
            return header[0]
        else:
            return ''

    def _get_block(self, line):
        block = self._re['block'].findall(line)
        if block:
            return block[0]
        else:
            return ''

    def _get_arg(self, line):
        return self._re['arg'].findall(line)

    def _is_arg(self, line):
        return bool(self._re['arg'].findall(line))


def _get_next_line(lines, linenumber):
    """
    Returns the next line but skips over any empty lines.
    An empty line is returned if read past the last line.
    """
    inc = linenumber + 1
    num_lines = len(lines)
    while True:
        if inc == num_lines:
            return ''
        if lines[inc]:
            return lines[inc]
        inc += 1


def parser(obj, choice='Google', args=None, returns=None, config=None):
    """
    Returns a new docstring parser based on selection. Currently, only the
    Google docstring syntax is supported.
    Args:
        obj : A dictionary that contains the docstring and other properties.
            This object is typically obtained by calling the `extract` function.
        choice: Keyword that determines the parser to use. Defaults to
            `'Google'`.
    Returns:
        A parser for the selected docstring syntax.
    Raises:
        NotImplementedError : This exception is raised when no parser is found.
    """
    parsers = {'Google': GoogleDocString}

    if choice in parsers:
        return parsers[choice](obj, args, returns, config)
    else:
        NotImplementedError(
            'The docstring parser `%s` is not implemented' % choice)


def get_config(default, config=None, warn=1):
    """
    Return a dictionary containing default configuration settings and any
    settings that the user has specified. The user settings will override the
    default settings.
    Args:
        default(dict) : A dictionary of default configuration settings.
        config(dict) : A dictionary of user-specified configuration settings.
        warn: Issue a warning if `config` contains an unknown key (not found in
            `default`).
    Returns:
        dict : User-specified configuration supplemented with default settings
            for field the user has not specified.
    """

    config_out = {}
    # Set defaults
    for key in default:
        config_out[key] = default[key]

    if not config:
        return config_out

    for key in config:
        if key not in default and warn:
            warnings.warn('Unknown option: %s in `config`' % key)
            # assert 0

    # Override defaults
    for key in config:
        config_out[key] = config[key]

    return config_out


def mark_code_blocks(txt, keyword='>>>', split='\n', tag="```", lang='python'):
    """
    Enclose code blocks in formatting tags. Default settings are consistent with
    markdown-styled code blocks for Python code.
    Args:
        txt: String to search for code blocks.
        keyword(optional, string): String that a code block must start with.
        split(optional, string): String that a code block must end with.
        tag(optional, string): String to enclose code block with.
        lang(optional, string) : String that determines what programming
            language is used in all code blocks. Set this to '' to disable
            syntax highlighting in markdown.
    Returns:
        string: A copy of the input with code formatting tags inserted (if any
        code blocks were found).
    """
    import re

    blocks = re.split('^%s' % split, txt, flags=re.M)
    out_blocks = []

    for block in blocks:
        lines = block.split(keyword)
        match = re.findall(r'(\s*)(%s[\w\W]+)' % keyword,
                           keyword.join(lines[1:]), re.M)
        if match:
            before_code = lines[0]
            indent = match[0][0]
            indented_tag = '%s%s' % (indent, tag)
            code = '%s%s' % (indent, match[0][1])
            out_blocks.append('%s%s%s\n%s%s' % (before_code, indented_tag,
                                                lang, code, indented_tag))
        else:
            out_blocks.append(block)
    return split.join(out_blocks)


class Extract:
    def __init__(self, path):
        self.path = path
        self.source = open(path).read()

    def get_function(self, function_name: str):
        """get_function

        returns a function if found in the top level of the current source file

        Args:
            function_name (str): name for function

        returns basic information for a method from the current source.

        Returns:
            header (dict): dictionary with the following keys:
                `class`: ''
                `docstring`: function docstring
                `signature`: formatted string with the function signature
                `lineno`: line number of the function in the source file
                `function`: 'function name'
                `ast`: ast Parse tree object matching the function
        """
        fn = self._get_function(function_name)

        signature = Extract._get_signature(fn)
        if signature:
            signature = f"{function_name}(\n{Extract._format_signature(signature)}\n)"
        else:
            signature = f"{function_name}()"

        return {
            "class": '',
            "docstring": ast.get_docstring(fn),
            "signature": signature,
            "lineno": fn.lineno,
            "function": fn.name,
            "ast": fn
        }

    def _get_function(self, function_name, classdef: ast.ClassDef = None):
        """ returns a function ast tree for the current function

        Raises:
            attribute error (AttributeError): if function not found in the current source

        Args:
            function_name (str): class name
            classdef (ast.ClassDef): (Default None) if not None it searches for a function inside
            the given ``ClassDef`` object

        Returns:
            class (ast.ClassDef): a class definition object taken from an ast tree

        """
        if classdef:
            body = classdef.body
        else:
            body = ast.parse(self.source).body

        for method_def in body:
            if isinstance(method_def, ast.FunctionDef) and method_def.name == function_name:
                return method_def

        if classdef:
            raise Exception("method %s not found in class %s" % (function_name, classdef.name))
        else:
            raise Exception("function %s not found in %s" % (function_name, self.path))

    def _get_class(self, class_name):
        """ returns a class ast tree for the current class name

        Raises:
            attribute error (AttributeError): if class not found in the current source

        Args:
            class_name (str): class name

        Returns:
            class (ast.ClassDef): a class definition object taken from an ast tree

        """
        node = ast.parse(self.source)

        for classdef in node.body:
            if isinstance(classdef, ast.ClassDef) and classdef.name == class_name:
                return classdef

        raise AttributeError(f"class {class_name} not found in file {self.path}")

    def get_methods(self, class_name, static=False):
        """ get_methods

        returns a list of methods from the current class name

        Args:
            class_name (str): class name for the class the methods belong to
            static (defaults to False): if true returns static methods only.

        Returns:
            methods (list): a list of method names

        """
        cls = self._get_class(class_name)
        methods = []
        for function in cls.body:
            if isinstance(function, ast.FunctionDef):
                if not function.decorator_list and \
                        not function.name == "__init__" and \
                        not function.name.startswith("_"):
                    methods.append(function.name)
                else:
                    for decorator in function.decorator_list:
                        if isinstance(decorator, ast.Name):
                            if static and decorator.id == 'staticmethod':
                                methods.append(function.name)
                            if not static and decorator.id != 'static':
                                # skip properties
                                pass
                                # methods.append(function.name)
        return methods

    def get_method(self, class_name, method_name):
        """get_method

        Args:
            class_name (str): name for the class this method belongs to
            method_name (str): name for the method

        returns basic information for a method from the current source.

        Returns:
            header (dict): dictionary with the following keys:
                `class`: parent class name for the current method
                `docstring`: method docstring
                `signature`: formatted string with the method signature
                `lineno`: line number of the class in the source file
                `function`: method name
                `ast`: ast Parse tree object for the method
        """

        cls = self._get_class(class_name)
        method = self._get_function(method_name, cls)

        signature = Extract._get_signature(method)
        if signature:
            signature = f"{method_name}(\n{Extract._format_signature(signature)}\n)"
        else:
            signature = f"{method_name}()"

        docstring = ast.get_docstring(method)
        if docstring is None:
            docstring = ""

        return {
            "class": cls.name,
            "docstring": docstring,
            "signature": signature,
            "lineno": method.lineno,
            "function": method.name,
            "ast": method
        }

    @staticmethod
    def _get_signature(function_def):
        source = astor.to_source(function_def.args)
        # remove 'self' and all whitespace
        source = re.sub(r'(?:self\,?)|\s', '', source)

        return source

    @staticmethod
    def _format_signature(signature_str):
        """ format signature

        format parameter string of the form ``param1, param2 = value2, ** params`` to
        separate parameters per line in such a way that we have no more than 80 characters
        per line

        Args:
            signature_str: signature string with params separated by a comma.

        Returns:
            signature(str): signature formatted to show parameters with no more than 80 characters per line


    """
        params = signature_str.split(',')
        lines = []
        tab = f"   "
        current_line = tab + f'{params.pop(0)}'
        while params:
            if len(current_line) + len(params[0]) > 77:
                lines.append(current_line + ",")
                current_line = tab
            else:
                if len(current_line) > len(tab):
                    current_line = f"{current_line}, {params.pop(0)}"
                else:
                    current_line = f"{current_line}{params.pop(0)}"
        if len(current_line) > len(tab):
            lines.append(current_line)
            return "\n".join(lines).replace(":", ": ").replace("=", " = ")
        else:
            return ''

    def get_docstring(self, get_lineno=False):
        node = ast.parse(self.source)
        docstring = ast.get_docstring(node)
        lineno = 0
        if docstring is None:
            docstring = ""
        else:
            lineno = node.body[0].lineno

        if get_lineno:
            return docstring, lineno
        else:
            return docstring

    def get_class(self, class_name: str):
        """ get_class

        returns basic information for a class from the current source.

        Returns:
            header(dict): dictionary with the following keys:
                `class `: class name
                `docstring`: class docstring
                `signature`: formatted string with the class signature
                `lineno`: line number of the class in the source file
                `function`: ''
                `ast`: ast Parse tree object for the class
        """

        class_def = self._get_class(class_name)

        try:
            init_method = self._get_function(function_name="__init__", classdef=class_def)
            signature = Extract._get_signature(init_method)
            if signature:
                signature = f"{class_name}(\n{Extract._format_signature(signature)}\n)"
        except AttributeError as e:
            raise e

        if not signature:
            signature = f"{class_name}()"
        docstring = ast.get_docstring(class_def)
        if docstring is None:
            docstring = ""

        if class_def:
            return {
                "class": class_def.name,
                "docstring": docstring,
                "signature": signature,
                "lineno": class_def.lineno,
                "function": "",
                "ast": class_def
            }

    def get_classes(self):
        """ get_classes

        returns a list of classes from the current module


        Returns:
            classes (list): a list of class names

        """
        module = ast.parse(self.source)

        return [node.name for node in module.body if isinstance(node, ast.ClassDef)]

    def get_functions(self):
        """ get_functions

        returns a list of functions from the current module

        Returns:
            functions (list): a list of function names

        """
        module = ast.parse(self.source)

        return [node.name for node in module.body if isinstance(node, ast.FunctionDef)]
