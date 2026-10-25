# ShelfLoop baseline report

100 synthetic scenarios; identical stock, demand, budget and cost assumptions.
Coverage is need packs covered; cash is purchases + transport in paise.

| Strategy | Scenario kind | Coverage % (mean) | Cash ₹ (mean) | Packs exchanged |
|---|---|---|---|---|
| manual | cooperative | 100.0 | 673 | 0.0 |
| manual | impossible | 0.0 | 0 | 0.0 |
| manual | unfavourable | 100.0 | 673 | 0.0 |
| pairwise_only | cooperative | 100.0 | 427 | 4.8 |
| pairwise_only | impossible | 0.0 | 0 | 0.0 |
| pairwise_only | unfavourable | 100.0 | 601 | 0.0 |
| replenishment_only | cooperative | 100.0 | 601 | 0.0 |
| replenishment_only | impossible | 0.0 | 0 | 0.0 |
| replenishment_only | unfavourable | 100.0 | 601 | 0.0 |
| shelfloop | cooperative | 100.0 | 322 | 8.6 |
| shelfloop | impossible | 0.0 | 0 | 0.0 |
| shelfloop | unfavourable | 100.0 | 601 | 0.0 |

Overall means:

- **manual**: coverage 80.0%, cash ₹538, packs exchanged 0.0
- **replenishment_only**: coverage 80.0%, cash ₹481, packs exchanged 0.0
- **pairwise_only**: coverage 80.0%, cash ₹376, packs exchanged 2.9
- **shelfloop**: coverage 80.0%, cash ₹313, packs exchanged 5.1

Caveat: inventory redeployed is not cash released; avoided expenditure is not measured savings. Synthetic scenarios only — field findings live in the pilot report.