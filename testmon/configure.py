import sys
from coverage.tracer import CTracer


def _is_debugger():
    return sys.gettrace() and not isinstance(sys.gettrace(), CTracer)


def _is_coverage():
    return isinstance(sys.gettrace(), CTracer)


def _is_xdist(options):
    return ("dist" in options and options["dist"] != "no") or "slaveinput" in options


def _get_notestmon_reasons(options, xdist):
    if options["no-testmon"]:
        return "deactivated through --no-testmon"

    if options["testmon_noselect"] and options["testmon_nocollect"]:
        return "deactivated, both noselect and nocollect options used"

    if not any(
        options[t]
        for t in [
            "testmon",
            "testmon_noselect",
            "testmon_nocollect",
            "testmon_forceselect",
        ]
    ):
        return "not mentioned"

    if xdist:
        return "deactivated, execution with xdist is not supported"

    return None


def _get_nocollect_reasons(
    options,
    debugger=False,
    coverage=False,
    dogfooding=False,
    cov_plugin=False,
):
    if options["testmon_nocollect"]:
        return [None]

    if coverage and not dogfooding:
        return ["it's not compatible with coverage.py"]

    if debugger and not dogfooding:
        return ["it's not compatible with debugger"]

    return []


def _get_noselect_reasons(options):
    if options["testmon_forceselect"]:
        return []

    elif options["testmon_noselect"]:
        return [None]

    if options["keyword"]:
        return ["-k was used"]

    if options["markexpr"]:
        return ["-m was used"]

    if options["lf"]:
        return ["--lf was used"]

    return []


def _formulate_deactivation(what, reasons):
    if reasons:
        return [
            f"{what} automatically deactivated because {reasons[0]}, "
            if reasons[0]
            else what + " deactivated, "
        ]
    else:
        return []


def _header_collect_select(
    options,
    debugger=False,
    coverage=False,
    dogfooding=False,
    xdist=False,
    cov_plugin=False,
):
    notestmon_reasons = _get_notestmon_reasons(options, xdist=xdist)

    if notestmon_reasons == "not mentioned":
        return None, False, False
    elif notestmon_reasons:
        return "testmon: " + notestmon_reasons, False, False

    nocollect_reasons = _get_nocollect_reasons(
        options,
        debugger=debugger,
        coverage=coverage,
        dogfooding=dogfooding,
        cov_plugin=cov_plugin,
    )

    noselect_reasons = _get_noselect_reasons(options)

    if nocollect_reasons or noselect_reasons:
        message = "".join(
            _formulate_deactivation("collection", nocollect_reasons)
            + _formulate_deactivation("selection", noselect_reasons)
        )
    else:
        message = ""

    return (
        f"testmon: {message}",
        not bool(nocollect_reasons),
        not bool(noselect_reasons),
    )


def header_collect_select(config, coverage_stack, cov_plugin=None):
    options = vars(config.option)
    return _header_collect_select(
        options,
        debugger=_is_debugger(),
        coverage=_is_coverage(),
        xdist=_is_xdist(options),
        cov_plugin=cov_plugin,
    )
