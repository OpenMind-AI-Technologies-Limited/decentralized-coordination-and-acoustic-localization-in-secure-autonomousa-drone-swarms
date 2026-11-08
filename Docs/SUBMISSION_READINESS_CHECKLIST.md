# Submission readiness checklist — software validation manuscript

**Manuscript:** `research_paper.md` (this branch); 27 verified and relevant cited scholarly/standards sources.
**Prepared:** 8 November 2026.
**Artifact scope:** software-only synthetic research, not hardware flight certification.
**Current archive source:** `d7393ba91166acd3b632cbb51a584b5611196edb`, evidence workflow [GitHub Actions run 42454145395](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/42454145395), 378 recorded trial rows across 63 settings.

## Completed
- Replaced the unsupported legacy paper claims with a correctly scoped original software-validation manuscript, including abstract, introduction, related research, implementation, threat model, methods, experiment table, raw results, figure captions, discussion, limitations, conclusions and declarations.
- Verified scholarly/standards DOIs rather than relying on earlier unsupported reference placeholders.
- Generated 5 data-grounded figure files as SVG in `figures/`; manuscript directly links them.
- Corrected wording of balanced partition outcomes (safe non-election is NOT leader convergence), virtual packet delay and conditional acoustic error.
- Preserved 27 numbered references, including an explicit citation/disclosure of the related Russian-language conference publication: DOI 10.58168/MIST2026_1425-1432.
- Prepared DOCX/PDF copies as external submission attachments. The older `Docs/Research-Paper.pdf` is **NOT** the new manuscript.
- Original evidence archive has been inspected for exact trial counts and numeric tables.
- Regression tests and manuscript updates are tracked in PR #3, not yet presumed merged.

## Journal-dependent or author-confirmation tasks
- [ ] Select target journal and apply its exact article category, word limit, figure/table policy, reference style and manuscript template. Until selected, the current document is **journal-neutral**, not guaranteed to satisfy a particular portal.
- [ ] Confirm the exact author name, university affiliation, ORCID and corresponding-author email; update title page and submission metadata.
- [ ] Confirm funding declaration; do not state 'none' unless verified by the author.
- [ ] Confirm competing interests / conflict-of-interest declaration and author contribution statement.
- [ ] Verify whether an overlapping cyber-resilience / command-authorization UAV swarm manuscript is under review. Disclose overlapping methods, related submissions and differences to the editor; do not duplicate simultaneously submitted results.
- [ ] Decide whether a persistent software/data DOI is required, archive the exact raw dataset and release tag accordingly, and insert its verified DOI. Do not invent a DOI.
- [ ] If the intended journal requires stronger experimental or formal proof, collect it first (at least more independent repetitions, recognized comparable baseline implementations, adversarial schedule analysis, and independent hardware/acoustic capture where claims demand).
- [ ] Final proofreading of language, disclosures, image accessibility, reference-metadata crosscheck, similarity policy and journal ethics forms.
- [ ] Reverify the current PR head's full CI and experiment-artifact job; only merge after the actual observed latest run passes.

## Important boundary
A reproducible paper **can be submitted as a software-validation study** only to a journal that accepts simulations and exploratory software evidence. These results **cannot** support full Byzantine consensus/liveness, arbitrary asynchronous network safety, real RF latency, UAV actuator safety, autonomous GNSS-denied navigation or field acoustic precision claims.

A green CI is not an editorial acceptance decision. The manuscript is structurally assembled and evidence-grounded; journal-specific and author-confirmation items remain open.