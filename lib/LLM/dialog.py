from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam, \
    ChatCompletionAssistantMessageParam, ChatCompletionSystemMessageParam
from pydantic import GetCoreSchemaHandler
from pydantic_core.core_schema import ValidatorFunctionWrapHandler
from pydantic_core import core_schema
from typing import Any


class Dialog:
    def __init__(self, system_message: str = None):
        self.messages: list[ChatCompletionMessageParam] = []
        if system_message:
            self.add_system_message(system_message)

    def add_system_message(self, message: str):
        self.messages.append(ChatCompletionSystemMessageParam(content=message, role="system"))

    def add_user_message(self, message: str):
        self.messages.append(ChatCompletionUserMessageParam(content=message, role="user"))

    def add_assistant_message(self, message: str):
        self.messages.append(ChatCompletionAssistantMessageParam(content=message, role="assistant"))

    def get_system_message(self) -> str | None:
        if self.messages and self.messages[0]["role"] == "system":
            return self.messages[0]["content"]
        return None

    def pop_message(self):
        self.messages.pop()

    def clear(self):
        system_message = self.get_system_message()
        self.messages.clear()
        if system_message:
            self.add_system_message(system_message)

    def size(self):
        return sum(len(message["content"]) for message in self.messages)

    def stringify(self, include_system=True) -> str:
        str_dialog = ''
        for message in self.messages:
            if not include_system and message["role"] == "system":
                continue
            str_dialog += f'---{message["role"]}---: {message["content"]}\n'
        return str_dialog

    def __str__(self):
        return self.stringify()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        def validate_dialog(value: Any, inner_handler: ValidatorFunctionWrapHandler) -> 'Dialog':
            """Wrap validator: called with (value, handler)"""
            if isinstance(value, cls):
                return value

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
