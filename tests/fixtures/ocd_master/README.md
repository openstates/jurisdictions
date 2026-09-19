# OCD Master Test Fixture

`mini_country_us.csv` is a controlled synthetic fixture for the OCD master
adapter. It mirrors the pinned `country-us.csv` header contract while keeping
normal tests offline and deterministic.

The fixture intentionally includes:

- country and state roots;
- county and place divisions;
- sibling places for same-parent suggestion tests; and
- leading-zero-safe string handling through literal OCD IDs.

It is not copied from the live source and must not be treated as production
data.
