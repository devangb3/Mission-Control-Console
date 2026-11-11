"""Application boundaries work without HTTP or concrete infrastructure."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from mission_control.domain.errors import InvalidReport, ModelCallError
from mission_control.application.ports import ReportBuilder, ReportStore
from mission_control.application.service import ReportService
from tests.support import reading


def test_invalid_input_never_runs_builder_or_storage() -> None:
    store = Mock(spec=ReportStore)
    builder = Mock(spec=ReportBuilder)
    service = ReportService(store, builder)
    with pytest.raises(InvalidReport):
        asyncio.run(service.create(reading(wind_knots=-1)))
    builder.build.assert_not_called()
    store.add.assert_not_called()


def test_failed_build_is_not_saved() -> None:
    store = Mock(spec=ReportStore)
    builder = Mock(spec=ReportBuilder)
    builder.build = AsyncMock(side_effect=ModelCallError("Unavailable"))
    with pytest.raises(ModelCallError):
        asyncio.run(ReportService(store, builder).create(reading()))
    store.add.assert_not_called()


def test_approval_normalizes_name_before_atomic_storage_operation() -> None:
    store = Mock(spec=ReportStore)
    service = ReportService(store, Mock(spec=ReportBuilder))
    result = service.approve("report-1", {"approver_name": "  Ada  "})
    store.approve.assert_called_once_with("report-1", "Ada")
    assert result is store.approve.return_value


@pytest.mark.parametrize("payload", [None, {}, {"approver_name": " "}, {"approver_name": "x" * 121}])
def test_invalid_approval_never_touches_storage(payload: object) -> None:
    store = Mock(spec=ReportStore)
    with pytest.raises(InvalidReport):
        ReportService(store, Mock(spec=ReportBuilder)).approve("report-1", payload)
    store.approve.assert_not_called()
