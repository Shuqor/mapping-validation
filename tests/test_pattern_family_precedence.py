import core.validate as validate_module


def test_date_format_tokens_take_precedence_over_generic_length_mapping_family():
    condition = (
        'if K101 = "PETD-" then map as below '
        'if length (K102) = 8 then map "CCYYMMDD" to Target '
        'if length (K102) = 12 then "CCYYMMDDHHMM" to Target'
    )

    assert validate_module._detect_pattern_family(condition) == "date_format_mapping"


def test_plain_length_mapping_stays_in_length_based_family():
    condition = "if length(name) <= 5 then map name to Target | else | map name left (name,5) to Target"

    assert validate_module._detect_pattern_family(condition) == "length_based_mapping"
