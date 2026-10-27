# Player Intelligence: season-first beta

Plan and implementation:

1. Retain the existing single-season rating builder and per-season game history.
   They already reject mixed seasons. Each season starts from the same fixed
   100 reference prior; no previous-season performances or minutes carry over.
2. Make **Season · resets each year** the first/default Player Intelligence
   option. Label the primary sidebar entry as seasonal, identify the season in
   the header and explain the reset beside ratings and the season-progress chart.
3. Preserve the existing **Career · covered seasons** pooled calculation as an
   explicit secondary option. Retain coverage warnings and career/season links.
4. Verify identical seasonal performances have identical ratings regardless of
   a player's prior career, and test the deployed-view scope-switch round trip.

This changes presentation and navigation, not rating formulas or published data.
The season builder uses only that season's appearances, minutes and attributed
impact; the career view pools covered appearances with its existing fixed prior.
Age/years in the league are not direct inputs. More minutes can improve sample
reliability, but historical minutes do not improve a season-reset rating's sample.
Season Value accumulates only within the selected season; career totals remain
explicitly limited to covered games. Early-season estimates remain provisional.
No data rebuild, model change, migration, new scheduler or Live change is needed.
