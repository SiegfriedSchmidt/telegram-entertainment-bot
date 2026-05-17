from pydantic import GetCoreSchemaHandler
from pydantic_core.core_schema import ValidatorFunctionWrapHandler
from pydantic_core import core_schema
from typing import Any


class Dialog:
    def __init__(self):
        self.messages = []

    def add_user_message(self, message):
        self.messages.append({
            "role": "user",
            "content": message
        })

    def add_assistant_message(self, message):
        self.messages.append({
            "role": "assistant",
            "content": message
        })

    def pop_message(self):
        self.messages.pop()

    def clear(self):
        self.messages.clear()

    def size(self):
        return sum(len(message["content"]) for message in self.messages)

    def __str__(self):
        str_dialog = ''
        for message in self.messages:
            str_dialog += f'---{message["role"]}---: {message["content"]}\n'
        return str_dialog

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        def validate_dialog(value: Any, inner_handler: ValidatorFunctionWrapHandler) -> 'Dialog':
            """Wrap validator: called with (value, handler)"""
            if isinstance(value, cls):
                return value

            # Accept list of messages
            if isinstance(value, list):
                dialog = cls()
                dialog.messages = value
                return dialog

            # Accept dict with messages
            if isinstance(value, dict):
                dialog = cls()
                messages = value.get("messages") or value.get("message_list") or []
                if isinstance(messages, list):
                    dialog.messages = messages
                return dialog

            if value is None:
                return cls()

            # Let the inner handler try first (useful fallback)
            try:
                validated = inner_handler(value)
                if isinstance(validated, cls):
                    return validated
            except Exception:
                pass

            raise ValueError(f"Cannot convert {type(value).__name__} to Dialog")

        return core_schema.no_info_wrap_validator_function(
            validate_dialog,
            core_schema.any_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda dialog: {"messages": dialog.messages}
            )
        )
