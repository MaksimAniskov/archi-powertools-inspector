def reconstructOutput(mock_file) -> str:
    return "".join(map(lambda call: call.args[0], mock_file.write.call_args_list))
