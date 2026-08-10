# Hearings are owned by DCMS, Diary Entries by advocates

Two different records describe what happened to a Case on a given date: the
court's account of the listing, and the advocate's own account of it. They are
kept in separate tables with a strict ownership rule — **a refresh writes
Hearings and only Hearings, and can never create, alter or delete a Diary
Entry.**

The rule is deliberately about what refresh may *destroy*, not about who may
write a Hearing. Advocates do record Hearings: the judge announces the next date
in open court and the firm knows it that afternoon, days before the portal shows
it and sometimes instead of the portal ever showing it reliably. So a Hearing
carries its source — firm-recorded or court-reported — and a refresh takes over
the Hearing for a date it reports on, the court's version standing where the two
disagree. What refresh must never do is touch a Diary Entry, because that is the
only content in the system a person composed and cannot get back.

We considered one record per date with official and authored fields side by side.
It reads more naturally, but ownership would then run through the middle of a
single row, which is what makes "Refresh from DCMS" frightening to press: any
bug in the merge risks overwriting something an advocate wrote and cannot get
back. Keeping them apart means the destructive half of a refresh has no reach
into authored content at all, and gives difference detection a surface where
every field has exactly one writer.

It also fits the asymmetry in practice. Diary-worthy days often involve no
hearing — a client meeting, drafting, a trip to the sub-registrar — and plenty
of listings are never written up.

The consequence is that the Case timeline is a merged reading view over two
sources rather than a single table, and that two records on one date are normal
rather than a duplicate to be reconciled.

The same rule applies a second time, to status. A Case carries a **Court Status**
reported by DCMS and a **Firm Status** set by advocates, because the two
legitimately disagree: a disposed case under appeal is the firm's most active
work, and a case pending for years with an unresponsive client is not active at
all. Every list and dashboard filters on Firm Status; the court's status is
displayed but never drives our workflow. Wherever the court's account and the
firm's account of the same thing can differ, they get separate fields with one
writer each.
