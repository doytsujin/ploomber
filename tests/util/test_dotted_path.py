from pathlib import Path
from unittest.mock import Mock

import parso
from test_pkg import functions
import pytest

from ploomber.util import dotted_path
from ploomber.exceptions import SpecValidationError


@pytest.mark.parametrize('spec', [
    'test_pkg.functions.some_function',
    {
        'dotted_path': 'test_pkg.functions.some_function'
    },
])
def test_call_spec(monkeypatch, spec):
    mock = Mock()
    monkeypatch.setattr(functions, 'some_function', mock)

    dotted_path.call_spec(spec)

    mock.assert_called_once_with()


def test_call_spec_with_kwargs(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(functions, 'some_function', mock)

    spec = {
        'dotted_path': 'test_pkg.functions.some_function',
        'a': 1,
        'b': 2,
    }

    dotted_path.call_spec(spec)

    mock.assert_called_once_with(a=1, b=2)


def test_call_spec_without_dotted_path_key():
    spec = {'a': 1}

    with pytest.raises(SpecValidationError) as excinfo:
        dotted_path.call_spec(spec)

    assert excinfo.value.errors == [{
        'loc': ('dotted_path', ),
        'msg': 'field required',
        'type': 'value_error.missing'
    }]


@pytest.mark.parametrize('kwargs, expected', [
    [None, 42],
    [dict(a=1), 1],
])
def test_call_dotted_path(tmp_directory, add_current_to_sys_path,
                          no_sys_modules_cache, kwargs, expected):

    Path('my_module.py').write_text("""
def function(a=42):
    return a
""")

    assert dotted_path.call_dotted_path('my_module.function',
                                        kwargs=kwargs) == expected


def test_call_dotted_path_unexpected_kwargs(tmp_directory,
                                            add_current_to_sys_path,
                                            no_sys_modules_cache):

    Path('my_module.py').write_text("""
def function():
    pass
""")

    with pytest.raises(TypeError) as excinfo:
        dotted_path.call_dotted_path('my_module.function', kwargs=dict(a=1))

    expected = ("function() got an unexpected keyword argument 'a' "
                "(Loaded from:")
    assert expected in str(excinfo.value)


_two = """
def some_name():
    pass

def some_name():
    pass
"""

_nested_before = """
def something():
    def some_name():
        pass

def some_name():
    pass
"""

_nested_after = """
def some_name():
    pass

def something():
    def some_name():
        pass
"""

_decorated = """
@some_dectorator
def some_name():
    pass
"""

_decorated_many = """
@some_decorator
@another_dectorator
def some_name():
    pass
"""

_test_many_names = """
def another():
    some_name = 1

some_name = 1

def some_name():
    some_name = pd.read_csv('aa')
    x['some_name']
    fn(some_name)
"""


@pytest.mark.parametrize('source, loc_expected', [
    [_test_many_names, 'function.py:7'],
    [_two, 'function.py:5'],
    [_nested_before, 'function.py:6'],
    [_decorated, 'function.py:3'],
    [_decorated_many, 'function.py:4'],
    [_nested_after, 'function.py:2'],
],
                         ids=[
                             'test-many-name',
                             'two',
                             'nested-before',
                             'decorated',
                             'decorated-many',
                             'nested-after',
                         ])
def test_check_defines_function_with_name(tmp_directory,
                                          add_current_to_sys_path,
                                          no_sys_modules_cache, source,
                                          loc_expected):
    Path('function.py').write_text(source)

    loc, source = dotted_path._check_defines_function_with_name(
        'function.py', 'some_name', None)

    assert loc == loc_expected


_overwritten_int = """
def name():
    pass

name = 1
"""

_overwritten_multi = """
def name():
    pass

name, x = 1, 2
"""

_overwritten_import = """
def name():
    pass

import name
"""

_overwritten_from_import = """
def name():
    pass

from something import name
"""

_overwritten_class = """
def name():
    pass

class name:
    pass
"""


@pytest.mark.parametrize('source', [
    _overwritten_int,
    _overwritten_import,
    _overwritten_from_import,
    _overwritten_multi,
    _overwritten_class,
])
def test_check_last_definition_is_function(source):

    module = parso.parse(source)

    with pytest.raises(TypeError) as excinfo:
        dotted_path._check_last_definition_is_function(module, 'name',
                                                       'x.name')

    assert ("Failed to load dotted path 'x.name'. "
            "Expected last defined 'name' to be a function. Got:"
            in str(excinfo.value))


# TODO: test many names but last one is correct
# -sub test case: with decorator

# TODO nested alias, should be skipped>?""
# TODO: test ignores other imports that do not alias
# try more than one alias


@pytest.mark.parametrize('import_', [
    'from pkg import some_name',
    'from pkg.sub import some_name',
    'from . import some_name',
    'from .pkg import some_name',
    'from .pkg.sub import some_name',
    'from .pkg.sub import some_name, another_name',
    'from pkg import some_name, another_name',
    'from pkg.sub import some_name, another_name',
])
def test_check_defines_function_with_name_detects_aliasing(
        tmp_directory, add_current_to_sys_path, no_sys_modules_cache, import_):
    Path('function.py').write_text(import_)

    with pytest.raises(NotImplementedError):
        dotted_path._check_defines_function_with_name('function.py',
                                                      'some_name', None)


@pytest.mark.parametrize('dotted_path_str', ['a.b', 'a.b.c'])
def test_lazily_locate_dotted_path_error_if_no_package_spec(dotted_path_str):

    with pytest.raises(ModuleNotFoundError) as excinfo:
        dotted_path.lazily_locate_dotted_path(dotted_path_str)

    assert (f"Error processing dotted path '{dotted_path_str}', no "
            "module named 'a'" in str(excinfo.value))


@pytest.mark.parametrize('dotted_path_str', ['a', 'a..b.c'])
def test_lazily_locate_dotted_path_error_if_invalid_dotted_path(
        dotted_path_str):
    with pytest.raises(ValueError) as excinfo:
        dotted_path.lazily_locate_dotted_path(dotted_path_str)

    expected = (f"Invalid dotted path '{dotted_path_str}'. "
                "Value must be a dot "
                "separated string, with at least two parts: "
                "[module_name].[function_name]")
    assert str(excinfo.value) == expected


def test_lazily_locate_dotted_path_missing_module(tmp_directory,
                                                  add_current_to_sys_path,
                                                  no_sys_modules_cache):
    Path('a').mkdir()
    Path('a', '__init__.py').touch()

    with pytest.raises(ModuleNotFoundError) as excinfo:
        dotted_path.lazily_locate_dotted_path('a.b.c')

    assert "No module named 'a.b'. Expected to find one of" in str(
        excinfo.value)
