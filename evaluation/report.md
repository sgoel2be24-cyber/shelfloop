# ShelfLoop baseline report

100 reproducible synthetic scenarios; no field outcomes.
Every strategy receives identical stock, needs, budgets and supplier quotes.
Manual means deterministic first-come purchasing, not an observed shopkeeper baseline.
Gross cash includes purchases, positive balancing obligations and exact transport shares.
External spend is purchases plus transport; it excludes cash paid between participating shops.
Transport uses one call-out per selected cycle plus pack-distance charges.

| Strategy | Scenario kind | Coverage % | Gross cash INR | External spend INR | Packs moved |
|---|---|---:|---:|---:|---:|
| manual | cooperative | 100.0 | 600.60 | 600.60 | 0.0 |
| manual | impossible | 0.0 | 0.00 | 0.00 | 0.0 |
| manual | unfavourable | 100.0 | 601.19 | 601.19 | 0.0 |
| replenishment_only | cooperative | 100.0 | 600.60 | 600.60 | 0.0 |
| replenishment_only | impossible | 0.0 | 0.00 | 0.00 | 0.0 |
| replenishment_only | unfavourable | 100.0 | 601.19 | 601.19 | 0.0 |
| pairwise_only | cooperative | 100.0 | 490.09 | 457.55 | 6.5 |
| pairwise_only | impossible | 0.0 | 0.00 | 0.00 | 0.0 |
| pairwise_only | unfavourable | 100.0 | 601.19 | 601.19 | 0.0 |
| shelfloop | cooperative | 100.0 | 432.06 | 375.87 | 10.0 |
| shelfloop | impossible | 0.0 | 0.00 | 0.00 | 0.0 |
| shelfloop | unfavourable | 100.0 | 601.19 | 601.19 | 0.0 |

## Overall means

- **manual**: coverage 80.0%; gross cash INR 480.59; external spend INR 480.59; mean runtime 0.03 ms.
- **replenishment_only**: coverage 80.0%; gross cash INR 480.59; external spend INR 480.59; mean runtime 5.61 ms.
- **pairwise_only**: coverage 80.0%; gross cash INR 414.29; external spend INR 394.77; mean runtime 9.68 ms.
- **shelfloop**: coverage 80.0%; gross cash INR 379.47; external spend INR 345.76; mean runtime 14.54 ms.

## Equivalent-fulfilment comparison

- Versus manual: 100/100 identical per-need fulfilment cases; aggregate gross-cash reduction 21.0%. Other cases are excluded from this cash comparison.
- Versus replenishment_only: 100/100 identical per-need fulfilment cases; aggregate gross-cash reduction 21.0%. Other cases are excluded from this cash comparison.
- Versus pairwise_only: 100/100 identical per-need fulfilment cases; aggregate gross-cash reduction 8.4%. Other cases are excluded from this cash comparison.

## Limits

Candidate cycles are limited to two/three shops and one selected cycle per shop; all legs currently use the same pack count.
Generated cooperative/unfavourable/impossible case proportions are artificial, not observed market frequencies.
Statuses: {"HEURISTIC": 100, "OPTIMAL": 300}
Inventory redeployed is not cash released. Avoided expenditure is not measured savings.
Public synthetic fixtures make these results reproducible but do not establish adoption, commercial ROI or forecast accuracy.
