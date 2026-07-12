## ADDED Requirements

### Requirement: Endpoint lists screenings missing a poster

The web app SHALL expose `GET /api/screenings/missing-posters` that
returns a JSON array of screenings that have no image and have at least
one untried poster source remaining. The endpoint SHALL require the same
Bearer token auth as the import endpoint.

Each item in the response SHALL include at minimum: `id`, `movie_title`,
and `next_source` (the next untried source name, e.g. `"tmdb"` or
`"imdb"`).

#### Scenario: Returns screenings needing posters

- **WHEN** a GET request is made with a valid Bearer token
- **THEN** the response is HTTP 200 with a JSON array of screening
  objects missing a poster

#### Scenario: Returns empty array when none are missing

- **WHEN** all screenings already have an image or have exhausted all
  sources
- **THEN** the response is HTTP 200 with an empty JSON array `[]`

#### Scenario: Unauthorized GET request is rejected

- **WHEN** the request has no valid Bearer token
- **THEN** the response is HTTP 401

### Requirement: Endpoint accepts a poster URL and updates the screening

The web app SHALL expose `PATCH /api/screenings/{id}/poster` that accepts
`{ "url": "<image_url>", "source": "<source_name>" }`, downloads the
image, stores it (imgBB on production, local disk on dev), and updates
the screening record.

The endpoint SHALL record a poster fetch attempt via the existing
`create_attempt()` repository function with status `"success"` or
`"error"` accordingly. The endpoint SHALL require the same Bearer token
auth as the import endpoint.

#### Scenario: Valid poster URL is downloaded and saved

- **WHEN** a PATCH request is made with a valid token, a reachable image
  URL, and a known source name
- **THEN** the screening's `image`, `image_width`, and `image_height`
  fields are updated, a `success` attempt is recorded, and the response
  is HTTP 200 with `{ "image": "<stored_filename>" }`

#### Scenario: Screening not found returns 404

- **WHEN** the `{id}` in the path does not match any screening
- **THEN** the response is HTTP 404

#### Scenario: Image URL is unreachable or not a valid image

- **WHEN** the URL cannot be downloaded or the content is not a valid
  image
- **THEN** an `error` attempt is recorded and the response is HTTP 422
  with an error description

#### Scenario: Unauthorized PATCH request is rejected

- **WHEN** the request has no valid Bearer token
- **THEN** the response is HTTP 401

### Requirement: Poster endpoint records all attempt outcomes

Whether the image is saved or the download fails, the web app SHALL
record a `PosterFetchAttempt` row via the existing `create_attempt()`
function so that exhausted sources are tracked and the screening is
eventually marked for manual review.

#### Scenario: Failed download is recorded

- **WHEN** a PATCH request is made but the image cannot be downloaded
- **THEN** a `PosterFetchAttempt` with `status="error"` is created and
  the screening's image fields are not modified
