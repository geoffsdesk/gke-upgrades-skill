# GKE Version Matrix

## Release Channel Version Progression

Versions flow: Rapid → Regular → Stable

| Channel | Best for | New versions arrive | Support period |
|---------|----------|-------------------|----------------|
| Rapid | Dev/test, early feature access | First | Standard (14 months) |
| Regular (default) | Most production workloads | After Rapid validation | Standard (14 months) |
| Stable | Mission-critical, stability-first | After Regular validation | Standard (14 months) |
| Extended | Compliance, slow upgrade cycles | Same as Regular | Up to 24 months |

## Version Skew Policy

- **Control plane → nodes**: Nodes can be up to 2 minor versions behind the control plane
- **Control plane upgrades**: Must be sequential (cannot skip minor versions)
- **Node pool upgrades**: Can skip minor versions (but not recommended)
- **Example**: CP at 1.31, nodes can be 1.31, 1.30, or 1.29

## Support Timeline

Each minor version follows this lifecycle:
1. Appears in Rapid channel
2. Promoted to Regular (standard support begins, ~14 months)
3. Promoted to Stable
4. End of standard support at 14 months from Regular
5. Extended support continues for Extended channel clusters (up to 24 months total)
6. End of life -- forced upgrade for all remaining clusters

## Key Constraints

- Maintenance exclusions: max 180 days for "no minor or node upgrades"
- "No upgrades" exclusion: max 30 days
- After exclusion expires, GKE auto-upgrades to the channel's current target
- EOL clusters are force-upgraded regardless of exclusions
