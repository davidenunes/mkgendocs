import os
import shutil
import yaml
import pathlib
from mkgendocs.parse import GoogleDocString, Extract
import argparse
from mako.template import Template
import logging

logging.basicConfig(level=logging.INFO,
                    format=">%(message)s")

DOCSTRING_TEMPLATE = """
## if we are processing a method function
%if header['function']:
    %if header['class']:
${h3} .${header['function']}
    %else:
${h3} ${header['function']}
    %endif
%if not source is UNDEFINED:
[source](${source})
%endif
```python
.${signature}
```
%elif header['class']:
${h2} ${header['class']}
%if not source is UNDEFINED:
[source](${source})
%endif
```python 
${signature}
```

%endif 

%for section in sections:
    %if section['header']:

**${section['header']}**

    %else:
---
    %endif
    %if section['args']:
        %for arg in section['args']:
        %if arg['field']:
* **${arg['field']}** ${arg['signature']} : ${arg['description']}
        %else:
* ${arg['description']}
        %endif
        %endfor
    %endif
${section['text']}
%endfor
"""


def copy_examples(examples_dir, destination_dir):
    """Copy the examples directory in the documentation.

    Prettify files by extracting the docstrings written in Markdown.
    """
    pathlib.Path(destination_dir).mkdir(exist_ok=True)
    for file in os.listdir(examples_dir):
        if not file.endswith('.py'):
            continue
        module_path = os.path.join(examples_dir, file)
        extract = Extract(module_path)
        docstring, lineno = extract.get_docstring(get_lineno=True)

        destination_file = os.path.join(destination_dir, file[:-2] + 'md')
        with open(destination_file, 'w+', encoding='utf-8') as f_out, \
                open(os.path.join(examples_dir, file),
                     'r+', encoding='utf-8') as f_in:

            f_out.write(docstring + '\n\n')

            # skip docstring
            for _ in range(lineno):
                next(f_in)

            f_out.write('```python\n')
            # next line might be empty.
            line = next(f_in)
            if line != '\n':
                f_out.write(line)

            # copy the rest of the file.
            for line in f_in:
                f_out.write(line)
            f_out.write('```')


def to_markdown(target_info, template, rel_path, config):
    """ converts object data and docstring to markdown

    Args:
        target_info: object name, signature, and docstring
        template: markdown template for docstring to be rendered in markdown
        rel_path: relative path to current class sources
        config: mkgendocs config dict

    Returns:
        markdown (str): a string with the object documentation rendered in markdown

    """
    docstring = target_info['docstring']
    docstring_parser = GoogleDocString(docstring)
    try:
        docstring_parser.parse()
    except SyntaxError as e:
        e2 = f"Error while processing docstrings for {target_info['class']}.{target_info['function']}"
        raise Exception(e2 + ":\n\t" + str(e)).with_traceback(e.__traceback__)

    headers, data = docstring_parser.markdown()

    # if docstring contains a signature, override the source
    if data and "signature" in data[0]:
        signature = data[0]["signature"]
    else:
        signature = target_info['signature']

    lineno = target_info.get('lineno', None)
    lineno = f"#L{lineno}" if lineno else ""

    if "repo" in config:
        repo = os.path.join(config['repo'], "blob", config.get('version', 'master'), rel_path, lineno)

        # in mako ## is a comment
        markdown_str = template.render(header=target_info,
                                       source=repo,
                                       signature=signature,
                                       sections=data,
                                       headers=headers,
                                       h2='##', h3='###')
    else:
        markdown_str = template.render(header=target_info,
                                       signature=signature,
                                       sections=data,
                                       headers=headers,
                                       h2='##', h3='###')

    return markdown_str


def build_index(pages):
    # source->class->page
    # source->fn->page

    class_index = dict()
    function_index = dict()
    for page_data in pages:
        is_index = page_data.get("index", False)
        if not is_index:
            source = page_data['source']
            page = page_data["page"]
            if "classes" in page_data:
                classes = [list(cls)[0] if isinstance(cls, dict) else cls for cls in page_data["classes"]]
                classes = set(classes)
            else:
                classes = set()
            classes = sorted(classes)

            if "functions" in page_data:
                functions = [list(fn)[0] if isinstance(fn, dict) else fn for fn in page_data["functions"]]
                functions = set(functions)
            else:
                functions = set()
            functions = sorted(functions)

            if source not in class_index:
                class_index[source] = dict()
            if source not in function_index:
                function_index[source] = dict()

            for cls in classes:
                class_index[source][cls] = page

            for fn in functions:
                function_index[source][fn] = page

    return class_index, function_index


def generate(config_path):
    """Generates the markdown files for the documentation.

    # Arguments
        sources_dir: Where to put the markdown files.
    """

    root = pathlib.Path().absolute()
    logging.info("Loading configuration file")
    try:
        config = yaml.full_load(open(config_path))
    except yaml.parser.ParserError as e:
        raise Exception(f"invalid configuration {config_path} \n") from e
    sources_dir = config.get('sources_dir', 'docs/sources')
    repo = config.get('repo', None)
    if not sources_dir:
        sources_dir = "docs/sources"
    template_dir = config.get('templates', None)

    logging.info('Cleaning up existing sources directory.')
    if sources_dir and os.path.exists(sources_dir):
        shutil.rmtree(sources_dir)

    logging.info('Populating sources directory with templates.')
    if template_dir:
        if not os.path.exists(template_dir):
            raise FileNotFoundError("No such directory: %s" % template_dir)
        shutil.copytree(template_dir, sources_dir)

    # if there are no templates, sources are not created from the files copied
    if not os.path.exists(sources_dir):
        os.makedirs(sources_dir)

    readme = ""
    if os.path.exists('README.md'):
        readme = open('README.md').read()

    if template_dir and os.path.exists(os.path.join(template_dir, 'index.md')):
        index = open(os.path.join(template_dir, 'index.md')).read()
        index = index.replace('{{autogenerated}}', readme[readme.find('##'):])
    else:
        index = readme

    # TODO this and README are still hardcoded filenames
    if os.path.exists('CONTRIBUTING.md'):
        shutil.copyfile('CONTRIBUTING.md', os.path.join(sources_dir, 'contributing.md'))

    if os.path.exists('examples'):
        copy_examples(os.path.join('examples'),
                      os.path.join(sources_dir, 'examples'))

    with open(os.path.join(sources_dir, 'index.md'), 'w', encoding='utf-8') as f:
        f.write(index)

    logging.info("Generating docs ...")
    docstring_template = DOCSTRING_TEMPLATE
    if "docstring_template" in config:
        try:
            docstring_template = open(config["docstring_template"]).read()
        except FileNotFoundError as e:
            raise e
    markdown_template = Template(text=docstring_template)

    pages = config.get("pages", dict())
    # check which classes and functions are being documented
    logging.info("Building ref index...")
    cls_index, fn_index = build_index(pages)
    for page_data in pages:
        page = page_data['page']
        is_index = page_data.get("index", False)
        # build index page
        if is_index:
            source = os.path.join(root, page_data['source'])
            cls_specified = page_data.get("classes", [])
            fns_specified = page_data.get("functions", [])

            # logging.info(fn_index[source])
            extract = Extract(source)
            all_cls = extract.get_classes()
            all_fn = [fn for fn in extract.get_functions() if not fn.startswith("_")]

            # filter by specified
            for cls in cls_specified:
                if cls not in all_cls:
                    msg = f"{cls} specified in index page \"{page}\" could not be found in \"{source}\""
                    logging.error(msg)
                    raise ValueError(msg)
            for fn in fns_specified:
                if fn not in all_fn:
                    msg = f"{fn} specified in index page \"{page}\" could not be found in \"{source}\""
                    logging.error(msg)
                    raise ValueError(msg)

            if cls_specified:
                all_cls = cls_specified
            if fns_specified:
                all_fn = fns_specified

            source = page_data['source']
            if source in cls_index and len(cls_index[source]) > 0:
                all_cls = [cls_name for cls_name in all_cls if cls_name in cls_index[source]]
            if source in fn_index and len(fn_index[source]) > 0:
                all_fn = [fn_name for fn_name in all_fn if fn_name in fn_index[source]]

            # TODO this can be refactored into code that's a bit more clean
            markdown = ["## Classes\n"]
            for cls_name in all_cls:
                if cls_name in cls_index[source]:
                    url = cls_index[source][cls_name]
                    suffix = ".md"
                    if url.endswith(suffix):
                        url = url[:-len(suffix)]
                    url += f"#{cls_name}"
                    markdown += [f"[class {cls_name}](/{url}/)\n"]
                else:
                    markdown += [f"class {cls_name}\n"]
            markdown += ["\n\n"]
            markdown += ["## Functions"]

            for fn_name in all_fn:
                if fn_name in fn_index[source]:
                    url = fn_index[source][fn_name]
                    suffix = ".md"
                    if url.endswith(suffix):
                        url = url[:-len(suffix)]
                    url += f"#{fn_name}"
                    markdown += [f"[{fn_name}](/{url}/)\n"]
                else:
                    markdown += [f"{fn_name}\n"]
            markdown += ["\n\n"]

            markdown = "\n".join(markdown)
        # build class or function page
        else:
            source = os.path.join(root, page_data['source'])
            extract = Extract(source)

            markdown_docstrings = []
            page_classes = page_data.get('classes', [])
            logging.debug(f"page classes {page_classes}")
            # page_methods = page_data.get('methods', [])
            page_functions = page_data.get('functions', [])

            def add_class_mkd(cls_name, methods):
                class_spec = extract.get_class(cls_name)

                mkd_str = to_markdown(class_spec, markdown_template, page_data['source'], config)
                markdown_docstrings.append(mkd_str)

                if methods:
                    markdown_docstrings[-1] += "\n\n**Methods:**\n\n"
                    for method in methods:
                        logging.info(f"Generating docs for {cls_name}.{method}")
                        try:
                            method_spec = extract.get_method(class_name=cls_name,
                                                             method_name=method)
                            mkd_str = to_markdown(method_spec, markdown_template, page_data['source'], config)
                            markdown_docstrings[-1] += mkd_str
                        except NameError:
                            pass

            for class_entry in page_classes:
                if isinstance(class_entry, dict):
                    class_name = list(class_entry.keys())[0]
                    all_methods = set(extract.get_methods(class_name))
                    method_names = class_entry.get(class_name)
                    excluded = set()
                    included = set()
                    for method_name in method_names:
                        if method_name.lstrip().startswith("!"):
                            method_name = method_name[method_name.find("!") + 1:]
                            if len(method_name) > 0 and method_name in all_methods:
                                excluded.add(method_name)
                            elif method_name not in all_methods:
                                raise ValueError(f"{method_name} not a method of {class_name}")
                        else:
                            included.add(method_name)
                    if excluded:
                        excluded_str = "\n".join(excluded)
                        logging.info(f"\tExcluded: {excluded_str}")

                    if len(excluded) > 0 and len(included) == 0:
                        included.update()
                    logging.info(class_name)
                    add_class_mkd(class_name, included)
                else:
                    # add all methods to documentation
                    class_methods = extract.get_methods(class_entry)
                    add_class_mkd(class_entry, class_methods)

            for fn in page_functions:
                logging.info(f"Generating docs for {fn}")
                fn_info = extract.get_function(fn)
                markdown_str = to_markdown(fn_info, markdown_template, page_data['source'], config)
                markdown_docstrings.append(markdown_str)

            markdown = '\n----\n\n'.join(markdown_docstrings)

        # Either insert content into existing template or create new page
        page_name = page_data['page']
        path = os.path.join(sources_dir, page_name)
        if os.path.exists(path):
            page_template = open(path).read()

            if '{{autogenerated}}' not in page_template:
                raise RuntimeError('Template found for ' + path +
                                   ' but missing {{autogenerated}}'
                                   ' tag.')
            markdown = page_template.replace('{{autogenerated}}', markdown)
            logging.info(f"Inserting autogenerated content into template:{path}")
        else:
            markdown = "#\n\n" + markdown
            logging.info(f"Creating new page with autogenerated content:{path}")

        subdir = os.path.dirname(path)
        if not os.path.exists(subdir):
            os.makedirs(subdir)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(markdown)


def main():
    parser = argparse.ArgumentParser(description='Generate docs')
    parser.add_argument('-c', '--config', dest='config', help='path to config file', default="mkgendocs.yml")
    args = parser.parse_args()
    generate(args.config)


if __name__ == '__main__':
    main()
