import pytest
from pydantic import ValidationError

from src.models.organization import Organization, OrganizationClassificationEnum


def test_organization_create_with_required_fields() -> None:
    """Test creating an Organization with only required fields."""
    org = Organization(
        name="Seattle City Council",
    )

    assert org.name == "Seattle City Council"
    assert org.classification is None


def test_organization_create_with_all_fields() -> None:
    """Test creating an Organization with all fields."""
    org = Organization(
        name="Seattle Parks Department",
        other_names=["Parks", "Parks Dept"],
        url="https://www.seattle.gov/parks",
        classification=OrganizationClassificationEnum.DEPARTMENT,
    )

    assert org.name == "Seattle Parks Department"
    assert org.other_names == ["Parks", "Parks Dept"]
    assert str(org.url) == "https://www.seattle.gov/parks"
    assert org.classification == OrganizationClassificationEnum.DEPARTMENT


def test_organization_rejects_missing_name() -> None:
    """Test that Organization requires name field."""
    with pytest.raises(ValidationError):
        Organization(
            other_names=["Parks", "Parks Dept"],
        )


def test_organization_accepts_classification_as_string() -> None:
    """Classification coerces from its string value so YAML loads directly."""
    org = Organization(name="Seattle Parks Department", classification="department")

    assert org.classification == OrganizationClassificationEnum.DEPARTMENT


def test_organization_accepts_explicit_none_classification() -> None:
    """Test that classification may be set to None explicitly."""
    org = Organization(name="Seattle Parks Department", classification=None)

    assert org.classification is None


def test_organization_rejects_unknown_classification() -> None:
    """Test that classification is constrained to the defined enum values."""
    with pytest.raises(ValidationError):
        Organization(name="Seattle Parks Department", classification="parks_thing")
