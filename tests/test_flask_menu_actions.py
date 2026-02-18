# tests/test_flask_menu_actions.py
from adapters.flask_menu_actions import make_cast_field_magic_fn, make_use_field_item_fn


def test_flask_menu_action_builders_are_importable_without_pygame_dependency():
    assert callable(make_cast_field_magic_fn)
    assert callable(make_use_field_item_fn)
