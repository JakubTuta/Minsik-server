import typing

import google.protobuf.descriptor
import google.protobuf.message

_FieldDescriptor = google.protobuf.descriptor.FieldDescriptor


def _is_map(field: _FieldDescriptor) -> bool:
    return (
        field.message_type is not None
        and field.message_type.GetOptions().map_entry
    )


def _convert(field: _FieldDescriptor, value: typing.Any) -> typing.Any:
    if field.type == _FieldDescriptor.TYPE_MESSAGE:
        return message_to_dict(value)

    return value


def message_to_dict(
    message: google.protobuf.message.Message,
    only: typing.Optional[typing.Container[str]] = None,
) -> typing.Dict[str, typing.Any]:
    """Plain dict of a message with native Python types.

    Unlike MessageToDict this keeps 64-bit integers as ints and emits every field
    (or just those named in `only`). A field with presence (optional scalar, message)
    that was never set is None, so the wire contract decides what is null.
    """
    result: typing.Dict[str, typing.Any] = {}
    for field in message.DESCRIPTOR.fields:
        if only is not None and field.name not in only:
            continue
        value = getattr(message, field.name)
        if _is_map(field):
            value_field = field.message_type.fields_by_name["value"]
            result[field.name] = {k: _convert(value_field, v) for k, v in value.items()}
        elif field.is_repeated:
            result[field.name] = [_convert(field, item) for item in value]
        elif field.has_presence and not message.HasField(field.name):
            result[field.name] = None
        else:
            result[field.name] = _convert(field, value)

    return result
