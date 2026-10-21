from testmon.configure import _get_noselect_reasons


def _options(**overrides):
    # `lf` is deliberately missing: `-p no:cacheprovider` does not register `--lf`
    options = {
        "testmon_forceselect": False,
        "testmon_noselect": False,
        "keyword": "",
        "markexpr": "",
    }
    options.update(overrides)
    return options


def test_noselect_reasons_without_the_lf_option():
    assert _get_noselect_reasons(_options()) == []


def test_noselect_reasons_with_lf():
    assert _get_noselect_reasons(_options(lf=True)) == ["--lf was used"]


def test_noselect_reasons_with_lf_disabled():
    assert _get_noselect_reasons(_options(lf=False)) == []
