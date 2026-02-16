# OCDID Matching and Validation Criteria

The following document outlines my assumptions for OCDID matching and validation criteria. 
It is based on the following sources from  [Open Civic Data Specification](https://open-civic-data.readthedocs.io/en/latest/):
* [Identifiers](https://open-civic-data.readthedocs.io/en/latest/identifiers/), specifically the Division Identifiers section.
* [OCDEP 2: Division Identifiers](https://open-civic-data.readthedocs.io/en/latest/proposals/0002.html)

## Data Location

## Division ID Composition

* Division IDs expressed in format `ocd-division/country:<ISO-3166-1 alpha-2 code>(/<type>:<type_id>)*`
    * Division IDs consist of a `country` code and zero or more `type` and `type_id` groups.
    * All identifiers and their components are in lower case.
    * Parts of the identifier are separated by a forward slash (`/`).
* The `country code` is required and is a valid [ISO-3166-1 alpha-2] (https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) code. The default for this application is `us`.
* `type` specifies the type of boundary being referenced (country, state, etc.).
    * Valid characters:
      * lowercase UTF-8 letters
      * digits (`0` - `9`)
* `type_id` specifies the unique identifier for the boundary being referenced.
    * Valid characters:
      * lowercase UTF-8 letters
      * digits (`0` - `9`)
      * hyphens (`-`)
      * underscores (`_`)
      * tilde (`~`)
    * All characters must be valid Unicode code points.
    * All characters must be lowercase.
    * No spaces or other whitespace characters are allowed.