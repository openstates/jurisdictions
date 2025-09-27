from pydantic import BaseModel

def test_model():
    class sample_model(BaseModel):
        number: int

    test = sample_model(number=2)
    assert test.number == 2

