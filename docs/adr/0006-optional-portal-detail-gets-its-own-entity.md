# Optional or multi-valued portal detail gets its own entity, not more Case columns

The portal's case-details view carries blocks beyond what `Case` already holds
as columns: Crime Details (FIR/CR/police station — present only for
criminal-flavoured cases, absent from most) and Act & Section (a list, not a
scalar — a Case can be brought under several). We model both as their own
entities related to `Case`, rather than adding more nullable columns directly
on it.

`Case`'s existing columns (`case_type`, `court_status`, `filing_number`, and
so on) are things every Case has an opinion about, even when the value is
null — one value, always in the same place. Crime Details and Act & Section
are not that: one is absent for most Cases entirely, and the other is
naturally a list. Flattening either onto `Case` would mean six columns that
are `NULL` on nearly every row for the first, and either a capped set of
columns or a delimited string for the second — both worse than a table built
for the shape the data actually has. This also means a Case that is not
criminal-flavoured carries no trace of Crime Details at all, rather than a
row of nulls implying a question that was never asked.

We considered keeping everything as `Case` columns for consistency with what
was already there. Rejected: consistency with the wrong shape is not a virtue,
and it does not scale — every future optional or multi-valued block the
portal turns up (and more than these two will) would otherwise mean widening
`Case` indefinitely.
