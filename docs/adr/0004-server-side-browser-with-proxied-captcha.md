# Playwright runs on the server; the CAPTCHA is proxied to the advocate

The portal requires a human to read a CAPTCHA, but it does not require the human
to be looking at the portal. Playwright therefore runs headless on the office
server: it opens the search page, selects the court establishment, fills the
CINO, and then hands the CAPTCHA image — fetched through the browser's own
session, so the code matches — to our case page. The advocate types six digits
into our UI and the server submits the search.

Choosing the district and court is not optional, and not particular to one
search mode: the portal requires both before *any* of its search tabs — Case No,
CNR, Filing No, Party Name and the rest — becomes usable. This is confirmed from
direct use of the portal rather than inferred from its markup. It is why every
Case must sit in a Court that has been identified against the portal's own lists,
and why a Case is normally brought in by searching for it in the first place
(ADR-0005).

The alternative was a companion program on each advocate's machine driving a
visible browser. That is more faithful to "a normal user with a normal browser"
and puts no browser lifecycle on the server, but it means installing, updating
and debugging software on five machines, and refresh only works at a desk that
has it. Streaming the whole browser to the advocate was rejected as the heaviest
option, and one that puts a government website in front of advocates instead of
our own application.

What we take on in exchange is a live browser session per in-flight refresh,
which the server must own: a session is created when a refresh starts, is
abandoned if the advocate walks away, and is closed on success, failure or
timeout. The CAPTCHA lapses after about thirty seconds, so the search is
pre-filled completely **before** the image is shown, and the portal's own
CAPTCHA-refresh control is driven when it expires rather than starting over.

Nothing here attempts to read, guess or bypass the CAPTCHA. A person solves it
every time; see ADR-0003.
