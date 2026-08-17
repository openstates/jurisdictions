import pytest
from pydantic import ValidationError

from src.models.organization import Organization

def test_organization_create_with_required_fields() -> None:
    """Test creating an Organization with only required fields."""
    org = Organization(
        name="Seattle City Council",
    )

    assert org.name == "Seattle City Council"


def test_organization_create_with_all_fields() -> None:
    """Test creating an Organization with all fields."""
    org = Organization(
        name="Seattle Parks Department",
        common_names=["Parks", "Parks Dept"],
        url="https://www.seattle.gov/parks",
    )

    assert org.name == "Seattle Parks Department"
    assert org.common_names == ["Parks", "Parks Dept"]
    assert str(org.url) == "https://www.seattle.gov/parks"


def test_organization_rejects_missing_name() -> None:
    """Test that Organization requires name field."""
    with pytest.raises(ValidationError):
        Organization(
            common_names=["Parks", "Parks Dept"], 
        )
