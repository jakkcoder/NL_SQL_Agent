from app.services.filter_detection import message_has_search_filters


def test_simple_investor_list_has_no_filters():
    assert message_has_search_filters("show individual investors") is False


def test_active_investors_has_filters():
    assert message_has_search_filters("show active individual investors") is True


def test_plain_individual_list_has_no_filters():
    assert message_has_search_filters("show individual investors") is False
