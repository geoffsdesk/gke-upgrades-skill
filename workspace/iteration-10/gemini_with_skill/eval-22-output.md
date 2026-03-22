This "musical chairs" effect is a classic Kubernetes scheduling behavior that happens during standard **Surge upgrades**. 

### What is happening?
During a surge upgrade, GKE creates a few new nodes (based on your `maxSurge` setting), cordons a matching number of old nodes, and begins draining pods. 

However, the Kubernetes scheduler is simply looking for *any* valid, uncordoned node with available capacity to place the evicted pods. If you have slack capacity on other older nodes that haven't been cordoned yet, the scheduler will happily place the pods there. When GKE eventually cordons those nodes later in the upgrade cycle, the pods get evicted all over again.

### How to fix it

To completely eliminate this issue, you should change your node pool upgrade strategy from Surge to **Blue-Green** or **Autoscaled Blue-Green**.

These strategies solve the problem by **cordoning the entire old node pool all at once** before any draining begins. Because all the old nodes are cordoned simultaneously, the scheduler is forced to place the evicted pods exclusively on the newly provisioned nodes.

Here is how to apply the fix based on your resource availability:

#### Option 1: Autoscaled Blue-Green (Recommended for most)
This is the most cost-effective and safest approach. GKE cordons the entire old pool, but instead of creating all the new nodes at once, it scales up the new pool on-demand as pods are evicted.

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade \
  --standard-rollout-policy=batch-soak-duration=10s,batch-node-count=1
```
*(Note: You can adjust the batch node count and soak duration based on how fast you want the old nodes to drain).*

#### Option 2: Standard Blue-Green (If you need maximum speed)
This creates an exact 1:1 replica of your node pool upfront, cordons the old pool, and drains pods over to the new pool. 
*Constraint: This requires you to have enough compute quota to temporarily double the size of your node pool.*

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --standard-rollout-policy=batch-soak-duration=10s,batch-node-count=1
```

#### Option 3: Tweak Surge settings (If you cannot use Blue-Green)
If you cannot use Blue-Green strategies (for example, due to strict quota limits or using GPU instances without autoscaling capability), you are stuck with Surge. You can't strictly prevent "musical chairs" in Surge, but you can reduce the impact by maximizing the number of new nodes created upfront:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0
```
By setting `maxSurge` higher (e.g., 3, 5, or more depending on your quota), you flood the cluster with new capacity. This statistically increases the probability that the scheduler will pick a new node rather than an old one, though it doesn't guarantee it like Blue-Green does.