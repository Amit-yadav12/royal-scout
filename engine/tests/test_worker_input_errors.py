from royalscout.worker import _is_permanent_pack_error


def test_missing_superr_tables_are_permanent_input_errors():
    error = FileNotFoundError("SupeRR pack is missing required table(s): matches, competitions, mapping")
    assert _is_permanent_pack_error(error)


def test_other_missing_files_remain_retryable_worker_errors():
    assert not _is_permanent_pack_error(FileNotFoundError("source object not found"))
    assert not _is_permanent_pack_error(RuntimeError("worker temporarily unavailable"))
