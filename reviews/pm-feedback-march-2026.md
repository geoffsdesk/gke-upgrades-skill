# Feedback March 20th

# General feedback:

\* old versions  
\* more on auto-upgrade recommendations  
\* less on custom workflows, more our using our automation  
\* no channel should not be in recommendation (including associated exclusions)   
\* maintenance window gcloud change (duration)  
\* rollout sequencing \- only one channel recommendation today (regular is fine since it takes a while to go through the fleet or stable for even more stability but behind/delay on security patches of \+2 weeks)  
\*extended channel

-  make it clear that additional cost is only for the extended period  
- It should be one of the recommendations to migrate from no channel in fact, especially for those who want max control over EoS enforcement

\* add scheduled upgrade notification throughout (control plane scheduled upgrade notification will be in preview March 24\)

Others docs to input:

* GKE Upgrade Roadmap: [go/gke-upgrade-roadmap](http://go/gke-upgrade-roadmap)   
* GKE Upgrades:  [go/gke-safe-upgrades](http://go/gke-safe-upgrades) (cleaned up version, versus mine here: [https://docs.google.com/presentation/d/1khWbdxrldJuAQQbcRBpk4K-lyzb-hdvyqsvgPL8OCk0/edit?resourcekey=0-VyUJ9cv4aj2VjA70Sm\_x1Q](https://docs.google.com/presentation/d/1khWbdxrldJuAQQbcRBpk4K-lyzb-hdvyqsvgPL8OCk0/edit?resourcekey=0-VyUJ9cv4aj2VjA70Sm_x1Q))   
* GKE L400 academy:   
  * (See:Deep Dive: GKE Upgrades / Day1) [https://drive.google.com/open?id=1H4d5Q1A4GuPUGbJwqSPOwjuOeHBrX4fyL38YHybqxfQ](https://drive.google.com/open?id=1H4d5Q1A4GuPUGbJwqSPOwjuOeHBrX4fyL38YHybqxfQ)   
  * Recording: [https://drive.google.com/corp/drive/folders/193Aren20nFWm1x9MMJcXygMAKOmJz9KO?resourcekey=0-H8fWAHSMd-OI5qULvNy\_tA](https://drive.google.com/corp/drive/folders/193Aren20nFWm1x9MMJcXygMAKOmJz9KO?resourcekey=0-H8fWAHSMd-OI5qULvNy_tA)   
* [go/gke-upgrade-faq](http://goto.google.com/gke-upgrade-faq)  
* [GKE AI Maintenance and Upgrade User Guide](https://docs.google.com/document/d/1Gr_yLxc-ANPvcyvHCYU5NfJR_Wx02mWGFAAFO3C7-E0/edit?resourcekey=0-UMmaNEgkDVePe9wodXcHXQ&tab=t.0#heading=h.vfk69r2ckip9)

# New features addition (March-April)

* Control plane patch controls:   
  Customers who need tight control over control plane patches can now benefit from the following  
* GKE keeps control plane patches for 90 days after the patch  is removed from release channel stable & regular for the purpose of upgrade/downgrade  
* GKE now supports a Control plane Upgrade recurrence interval (for control plane patch & minor)

* Maintenance window duration field & timeline UX improvement  
  * We have a new maintenance window duration field available to simplify UX; This is the new UX that should be replaced throughout in all responses starting April 1st 2026

```
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start START_TIME \
    --maintenance-window-duration DURATION \
    --maintenance-window-recurrence RRULE
```

* Auto-upgrade Nodepool concurrency \- preview (end March)

We’re adding nodepool upgrade concurrency for auto-upgrades to speed up upgrades. [Add documentation for configuring concurrent node pool upgrades.](https://critique.corp.google.com/cl/878130889)

This should be available April 1st 2026

* Scheduled upgrade for the control plane \- preview (Available March 24\)

We’re adding scheduled upgrade notifications for the control plane (preview). Node scheduled upgrade notification will follow

# New FAQ (Added to FAQ as well)

## When should I use the extended channel?

In general, the best practice is to stay on standard support in the Regular or Stable channel for production workloads and use Rapid to test or qualify the latest functionality. 

Extended channel provides additional flexibility over Stable and Regular channels for customers who want maximum control and more flexibility around end of support enforcement. Customers are automatically opted-in extended support and pay extra for extended support during the extended support period. There is no extra charge during the standard support period.

### How do I ensure that patches dont affect my workloads?

In general patches contain minimum changes that are non disruptive.   
To get the best stability, we recommend a Canary strategy whereby a “canary” cluster is upgraded before the rest of production. This can be done using rollout sequencing (best practice), a mix of release channels (keep the minor version the same across the channels in steady state), or through custom workflows 

### When should you use the legacy no channel 

The “no channel” is a legacy channel that behaves like a release channel by default. We no longer recommend “no channel” and instead recommend release channels for maximum control. Unless you’re using a mix of workload in a cluster where some nodepools need auto-upgrades and others need tight control, there is no reason to use “no channel” and GKE is working on closing that gap for release channels

### When should you use the per nodepool exclusion versus the per cluster exclusion 

The per cluster exclusion on release channel is always preferred over per nodepool control as it ensures maximum control over both minor version and node version upgrade and prevent control plane and node minor version skew. There are times when you need to control every nodepool differently especially if you have a mix of nodepools. When that happens, you can use the per nodepool exclusion.

### When should I use GKE auto-upgrade versus user-initiated upgrade

By default, GKE auto-upgrades clusters to keep them secure and up-to-date. You can optimize auto-upgrades for your environment by controlling the timing of upgrades, the progression of upgrades through the fleet and nodepool upgrade strategies.

At times, you may want to control all upgrades and initiate them yourself only. This is especially true for disruption intolerant workloads and complex environments. GKE provides the control you need to disable auto-upgrade until end of support on both minor and nodes through exclusions.  GKE also provides advanced controls for control plane patches such as disruption interval.

### Help me understand when to choose each nodepool upgrade strategy

1. **Surge Upgrades**

   * **Description:** This is the default strategy. Nodes are upgraded in a rolling window. New nodes with the updated version are created, and old nodes are cordoned and drained before being deleted. You can control the speed and disruption by configuring `maxSurge` (how many extra nodes can be temporarily created) and `maxUnavailable` (how many nodes can be unavailable during the process).  
   * **When to Use:** Suitable for most general-purpose workloads, especially those that are stateless and can handle pods being rescheduled. It's a good balance between speed and resource consumption, as it doesn't require doubling the node capacity. Also use for AI inference and training workloads but adjust associated maxSurge and maxUnavailable settings for capacity constrained environments.  
   * **Workload Types:**  
     * Stateless applications (e.g., web servers, API gateways)  
     * Applications with multiple replicas where temporary unavailability of a few nodes is acceptable.  
     * Cost-sensitive workloads where spinning up a full set of new nodes is undesirable.  
     * AI inference workloads (optimize for limited capacity)  
     * AI training workloads (adjust concurrency, and optimize for limited capacity)  
2. **Blue-Green Upgrades**

   * **Description:** This strategy minimizes risk by keeping the old nodes (blue pool) available while new nodes with the updated version are provisioned (green pool). The blue pool is cordoned, and workloads are gradually drained to the green pool. This allows for a soaking period to validate workloads on the new configuration. Rollback is fast, as you can simply uncordon the blue pool if issues arise. This strategy typically requires enough quota to double the node pool size temporarily.  
   * **When to Use:** Ideal for environments where rollback capability and thorough validation on the new version are critical. Use when you need to minimize downtime and risk during the upgrade.  
   * **Workload Types:**  
     * Mission-critical applications.  
     * Stateful applications sensitive to node changes.  
     * Environments with strict testing and validation requirements before full cutover.  
     * Applications where a quick rollback path is essential.  
3. **Autoscaled Blue-Green Upgrades (Preview)**

   * **Description:** This is an enhancement of the Blue-Green strategy, designed to be more cost-effective and suitable for long-running workloads. The green node pool scales up as needed based on workload demand, while the blue node pool can be scaled down as pods are safely evicted and rescheduled. It supports longer eviction periods (wait-for-drain, longer graceful termination periods, PDB upgrade timeout), allowing pods to complete their work.  
   * **When to Use:** Best for disruption-intolerant workloads that need to run to completion.   
   * **Workload Types:**  
     * Long-running batch processing jobs.  
     * Game servers.  
     * Any workload sensitive to eviction that can benefit from a more controlled, autoscaled transition.

**Special Cases:**

* **Flex-start VMs:** These nodes use a strategy called "short-lived upgrades."

In summary:

* **Surge:** Best for most. Tune for concurrency and limited capacity.  
* **Advanced options:**  
  * **Blue-Green:** Best for maximum safety, validation, and fast rollbacks for critical apps.  
  * **Autoscaled Blue-Green:** Best for batch workloads and disruption-sensitive workloads requiring more time before eviction.


  

## Feedback.JSON

{

  "reviews": \[

    {

      "eval\_name": "eval-1",

      "feedback": "Note: \\n- 2-step minor upgrade with rollback safety for the 1st step is available on control plane\\n- nodepool: supports downgrade",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-2",

      "feedback": "\\"No minor or node upgrades\\" (up to EoS, allows security patches \- recommended) / an exclusion for nodes should not be recommended on autopilot unless customers asks specifically to exclude nodes",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-3",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-4",

      "feedback": "Related to rollback, GKE support a 2-step minor version upgrade with rollbacksatefy for the 1st step. this can help reduce risk further",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-5",

      "feedback": "I'd recommend skip-level upgrade with 2 version skip, but not the 3 level skip; In the past our recommendation for N+3 would have been start with skip-level upgrade \+ one more upgrade",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-6",

      "feedback": "Since you're moving to a slower channel, consider configuring maintenance exclusions for maximum controll \--\> this should not be recommended unless a customer wants the actual control. ",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-7",

      "feedback": "Reframe the question so it's not about 1.32-\>1.32; gcloud is not correct for rollout sequencing; Also staggering maintenance windows is not enough as a new version may be first available when the prod window opens. The staggering will happen but not guarantee dev before prod; An alternative would be to use two different channel with minor controls (so the 2 channels stay on the same minor)",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-8",

      "feedback": "surge parameters should just be ignored with blue green\\n",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-9",

      "feedback": "FOR ML / training workloads, custom upgrade strategy will likely still work better given the need to upgrade host at the same time as nodepool and the max concurrency required",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-10",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-11",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-12",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-13",

      "feedback": "For autoscaled blue-green, the gcloud options such as \--enable-autoscaling and \--autoscaled-rollout-olicy are missing and some of the configs are for blue-green only (not the autoscaled part)",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-14",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-15",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-16",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-17",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-18",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-19",

      "feedback": "\#\#\# \\ud83d\\udfe1 MEDIUM \- Plan Within 1-2 Weeks \--\> the scheduled upgrade notification is within 3 days (not 1 week)",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-20",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-21",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-22",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-23",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-24",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-25",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-26",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-27",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-28",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-29",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-30",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-31",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-32",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-33",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-34",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-35",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-36",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-37",

      "feedback": "",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-38",

      "feedback": "\#\#\# 2\. Add maintenance exclusions for maximum control \--\> where maximum control is needed (this is not for everyone, in fact it should be if you have disruption intolerant workloads)\\nFor production workloads, I recommend the \*\*\\"no minor or node upgrades\\"\*\* exclusion: \--\> Instead it should say for production workloads that require maximum control, I recommend...\\nDisruption interval is in seconds only today\\n- \*\*Canary pattern\*\* \\u2014 lift maintenance exclusions on one cluster first, validate, then the others \--\> it should instead say use rollout sequencing or a custom mechanism to sequence clusters ",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-39",

      "feedback": "The answer depends on the workload type and scale. In general for inference using the current strategy as per recommendation works, but if this is training upgrading all at once with custom strategies and upgrading the host at the same time would be more efficient",

      "timestamp": "2026-03-23T05:28:11.039Z"

    },

    {

      "eval\_name": "eval-40",

      "feedback": "--maintenance-minor-version-disruption-interval 90 \--\> note that disruption-interval is in seconds only, today so the chose 30/90 doesnt seem appropraite (see https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-disruption-budget\#configure-cdb)",

      "timestamp": "2026-03-23T05:28:11.039Z"

    }

  \],

  "status": "complete",

  "timestamp": "2026-03-23T05:28:11.042674+00:00"

}

  "reviews": \[

    {

      "eval\_name": "eval-1",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-2",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-3",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-4",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-5",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-6",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-7",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-8",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-9",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-10",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-11",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-12",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-13",

      "feedback": "Alternatively, GKE has a preview nodepool upgrade strategy autoscale blue-green and you can set the wait-for-drain time",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-14",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-15",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-16",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-17",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-18",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-19",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-20",

      "feedback": "USer skip-level upgrades for nodepools. Also GKE recommended auto-upgrades as the default and you can set the controls you need such as timing, sequencing, and nodepool upgrade strategies",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-21",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-22",

      "feedback": "Alternatively use autoscaled blue green upgrades (in preview) to cordon the nodepool",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-23",

      "feedback": "It is good to reiterate that there is a GKE PDB timeout that applies and GKE has notifications sent when eviction is blocked by PDB",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-24",

      "feedback": "1 \- AND per nodepool maintenance exclusion\\nThe difference is that Release Channel also supports per minor exclusion and cluster level exclusions\\n\\nExtended channel should be one of the migration path tp \[rpvode more flexible EoS enforcement\\n\\nWhen  moving from no channels to release channels and vice versa with maintenance exclusion per nodepool auto-upgrade disabled, follow specific guidance to add a \\"no upgrades\\" exclusion termporary and translate exclusion for release channel/no channel as some exclusions dont translate 1 to 1 and may be ignored",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-25",

      "feedback": "default \- typically the same as auto-upgrade target but there can be differences when new minor versions are introduced \\n\\"any users think \\"default\\" \= \\"what my cluster upgrades to\\" \\u2014 but that's wrong.\\" \--\> this is abit strong as in most cases it is true but there is a specific distinction (separatestage) especially for new minor version introduction\\n\\nNote \- for a given release channel, there can be different auto-upgrade target as some cluster may have policies in place restricting minor versions (say you are on minor 1.34 with a no minor upgrades exclusions, you can still have an auto-upgrade target to 1.34.x even though this is different from the \\"Recommended\\" auto-upgrade for the channel. It is cluster specific",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-26",

      "feedback": "Legacy channel behavior at EoS: control plane eos minor version are auto-upgraded to next supported minor version; EoS nodepools are auto-upgraded to the next supported version (Even when \\"no  auto-upgrade is configured). Note that currently maintenance exclusions dont translate between no channel and release channels except for type \\"no upgrades\\". Ensure that you use the known exclusion when moving from no channel to release channels and vice versa",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-27",

      "feedback": "Review recommendation for extended (avoid extended...) Extended would be important if customer wants control over EoS enforcement (wait for extended end of support enforcement)\\n\\nNo minor or node exclusion should track the end of support date (eos date auto-renewed with new minor version). \--add-maintenance-exclusion-until-end-of-support\\nThere is no longer a 6month max (no need to chain them) \\n\\n(Advanced) Customer may also want to control the sequencing of upgrades with rollout sequencing and the frequency of control plane patches with the cluster disruption budget (disruption interval)\\n\\nExtended support \- additional cost is only during the extended period\\nDoes not auto-upgrade cluster minor version until end of extended support (you are responsible for the control plane minor version upgrade)",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-28",

      "feedback": "\# Release cadence also has an element of release channel promotion (from Rapid to Regular to stable)\\n\\nAlso if you want ultimate predictability (the upgrade will happen at this time during this maintenance window), then you can initiate the upgrade instead of waiting for it to happen automatically",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-29",

      "feedback": "Permanent Minor Version Control should be of scope \\"no minor\\"; \\"no minor or nodes\\" is if they also want to stop node upgrades; Also the maintenance exclusion that is permanent and tracks the eos has a different setting without an explicit set date but with option \--add-maintenance-exclusion-until-end-of-support",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-30",

      "feedback": "We also have an API to assess zzhttps://clouddocs.devsite.corp.google.com/kubernetes-engine/docs/release-schedule\#schedule-for-release-channels ; Example gcloud container clusters get-upgrade-info cluster-5 \--region us-central1\\nautoUpgradeStatus:\\n- ACTIVE\\nendOfExtendedSupportTimestamp: '2027-06-03'\\nendOfStandardSupportTimestamp: '2026-08-03'\\nminorTargetVersion: 1.34.4-gke.1047000\\npatchTargetVersion: 1.33.8-gke.1026000",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-31",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-32",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-33",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-34",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-35",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-36",

      "feedback": "If there is limited capacity, we should assume a reservation and there would not be any capacity for blue/green (2x resources). We should follow instructions for GKE AI maintenance here",

      "timestamp": "2026-03-20T22:27:37.978Z"

    },

    {

      "eval\_name": "eval-37",

      "feedback": "",

      "timestamp": "2026-03-20T22:27:37.978Z"

    }

  \],

  "status": "complete",

  "timestamp": "2026-03-20T22:27:37.998165+00:00"

}

# Feedback March 21st

Questions to ask:

**What is the risk of upgrade for cluster x?**  
Nice response: [https://screenshot.googleplex.com/BZ5BWvJT6LZsiRu](https://screenshot.googleplex.com/BZ5BWvJT6LZsiRu)

**Can do better:**

* Did not find my scheduled upgrade notification: [https://screenshot.googleplex.com/37ZhLBMtcdfcQKp](https://screenshot.googleplex.com/37ZhLBMtcdfcQKp)   
* “Minor patch upgrade” terminology is confusing…. It’s either minor or patch version

**When is my next upgrade scheduled on cluster 3?**   
Using /gke:plan  
[https://pantheon.corp.google.com/logs/query;query=resource.type%3D%22gke\_clus...](https://screenshot.googleplex.com/5N2AkbRnb73FSwD)

**What is the expected timeline for next auto-upgrades in my project?**  
Response looks nice, but why not use GKE release schedule as source of truth and clarify that this is a best case scenario subject to change [https://screenshot.googleplex.com/pfeqveuujewRvQw](https://screenshot.googleplex.com/pfeqveuujewRvQw) 

**Do I have any cluster nearing end of support?**  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/9Dj6Bs3FmzhEMCV)

Looks nice though it didnt pick up immediate changes and and I had to prompt to get it to add nodepool  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/3hXd7ShT68adsYo)

**When is version x expected to reach stable?**  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/5GnYSaieYKd2sbQ)  
Nice response

**How does my configuration on cluster x deviate from best practices?**  
**[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/7n7MV5cDtieNjvK)**

**What are the latest features I should know about that help with GKE upgrades?**  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/Lut4uCeWskcmsMd)

**Why is EoS enforced on my nodepool in no channel? EKS doesnt enforce EoS on nodepool that we manage?**  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/8hcgkpVjRjnhZn6)  
It’s a bit negative and the comparison is a bit strange

**How long is a version available in release channels for?**  
**[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/Btj6dfu7ZAer6fY)**

**How do I configure upgrade for fedramp compliance?**  
[https://remotedesktop.corp.google.com/access/session/55650673-963d-4d65-a132-...](https://screenshot.googleplex.com/69cdkpbuSRSRFrp)  
 

# Feedback March 22nd

**Evals improvements (reviewed 1-13)**

**Notes:**

* Maintenance exclusions \- dont recommend use unless customer actually wants the control (ex. Autopilot eval)  
    
* ML workloads \- use custom upgrade strategy instead of autoscaled b/g still has the same node concurrency max batch count  
    
* Gcloud seems wrong for recommendations on rollout sequencing and autoscaled blue green  
  * [`https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-pool-upgrade-strategies#configure-autoscaled-blue-green`](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-pool-upgrade-strategies#configure-autoscaled-blue-green)  
  * [`https://docs.cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing-custom-stages/manage-upgrades-with-rollout-sequencing#create-rollout-sequence-custom-stages`](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing-custom-stages/manage-upgrades-with-rollout-sequencing#create-rollout-sequence-custom-stages) 

* Lots of eval now have upgrade from 1.32 \-\> 1.32? Did we mean to say 1.32-\>1.33?  
    
* Clarify rollback support for control plane, nodepool in FAQ → already addressed

* Generally missing specific info on how to check for API deprecations gcloud commands:

Current  
\# Check for deprecated API usage (most common upgrade blocker)  
kubectl get \--raw /metrics | grep apiserver\_request\_total | grep deprecated

From docs:

When GKE detects that a cluster is using a Kubernetes feature or API that is deprecated and will be removed in an upcoming minor version, the following happens:

* [Automatic upgrade](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades#upgrading_automatically) to the upcoming minor version is paused. To learn more about how this works, see [What happens when GKE pauses automatic upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations#auto-upgrade-pause).  
* An insight and recommendation are generated so that you can assess and mitigate your cluster's exposure to the deprecation.

```
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID \
    --format=FORMAT \
    --filter="insightSubtype:SUBTYPE"
```

* Dev & Prod channel \- generally should be on the same channel or one channel apart with the same minor version (with no minor exclusion with user triggered minor upgrades)

* Upgrade timeline typical between rapid, regular, Stable is different between minor version and patches  
* 

The typical time depends on whether this is a new minor version progressing or a patch version. Patch versions typically take \~2 week per stage (ex. Between Rapid target and regular target)

* Rapid (available)--\> (+7days) Rapid (target) → (+7days) Regular (available) → (+7days) Regular (target) → (+7days) Stable (available) → (+7days) Stable (target)

Minor version progression is more complex and can take time. The best is to check the GKE release schedule for historical info and expectations

* 

* Notification \- eviction blocked y PDB/tgps

Note for questions PDB, we have a notification now to keep track of eviction blocked by PDB   
`https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-notifications#disruption-event`

Node version skew best practice

* Keep a version skew maximum of (N-2) between the control plane and node. Best practice is to stay on the same minor version between the control plane and node and stay on version skew during upgrade operations.

## Feedback.json

{  
  "reviews": \[  
    {  
      "eval\_name": "eval-1",  
      "feedback": "Note: \\n- 2-step minor upgrade with rollback safety for the 1st step is available on control plane\\n- nodepool: supports downgrade",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-2",  
      "feedback": "\\"No minor or node upgrades\\" (up to EoS, allows security patches \- recommended) / an exclusion for nodes should not be recommended on autopilot unless customers asks specifically to exclude nodes",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-3",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-4",  
      "feedback": "Related to rollback, GKE support a 2-step minor version upgrade with rollbacksatefy for the 1st step. this can help reduce risk further",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-5",  
      "feedback": "I'd recommend skip-level upgrade with 2 version skip, but not the 3 level skip; In the past our recommendation for N+3 would have been start with skip-level upgrade \+ one more upgrade",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-6",  
      "feedback": "Since you're moving to a slower channel, consider configuring maintenance exclusions for maximum controll \--\> this should not be recommended unless a customer wants the actual control. ",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-7",  
      "feedback": "Reframe the question so it's not about 1.32-\>1.32; gcloud is not correct for rollout sequencing; Also staggering maintenance windows is not enough as a new version may be first available when the prod window opens. The staggering will happen but not guarantee dev before prod; An alternative would be to use two different channel with minor controls (so the 2 channels stay on the same minor)",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-8",  
      "feedback": "surge parameters should just be ignored with blue green\\n",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-9",  
      "feedback": "FOR ML / training workloads, custom upgrade strategy will likely still work better given the need to upgrade host at the same time as nodepool and the max concurrency required",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-10",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-11",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-12",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-13",  
      "feedback": "For autoscaled blue-green, the gcloud options such as \--enable-autoscaling and \--autoscaled-rollout-olicy are missing and some of the configs are for blue-green only (not the autoscaled part)",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-14",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-15",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-16",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-17",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-18",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-19",  
      "feedback": "\#\#\# \\ud83d\\udfe1 MEDIUM \- Plan Within 1-2 Weeks \--\> the scheduled upgrade notification is within 3 days (not 1 week)",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-20",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-21",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-22",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-23",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-24",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-25",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-26",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-27",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-28",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-29",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-30",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-31",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-32",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-33",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-34",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-35",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-36",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-37",  
      "feedback": "",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-38",  
      "feedback": "\#\#\# 2\. Add maintenance exclusions for maximum control \--\> where maximum control is needed (this is not for everyone, in fact it should be if you have disruption intolerant workloads)\\nFor production workloads, I recommend the \*\*\\"no minor or node upgrades\\"\*\* exclusion: \--\> Instead it should say for production workloads that require maximum control, I recommend...\\nDisruption interval is in seconds only today\\n- \*\*Canary pattern\*\* \\u2014 lift maintenance exclusions on one cluster first, validate, then the others \--\> it should instead say use rollout sequencing or a custom mechanism to sequence clusters ",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-39",  
      "feedback": "The answer depends on the workload type and scale. In general for inference using the current strategy as per recommendation works, but if this is training upgrading all at once with custom strategies and upgrading the host at the same time would be more efficient",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    },  
    {  
      "eval\_name": "eval-40",  
      "feedback": "--maintenance-minor-version-disruption-interval 90 \--\> note that disruption-interval is in seconds only, today so the chose 30/90 doesnt seem appropraite (see https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-disruption-budget\#configure-cdb)",  
      "timestamp": "2026-03-23T05:28:11.039Z"  
    }  
  \],  
  "status": "complete",  
  "timestamp": "2026-03-23T05:28:11.042674+00:00"  
}

# Feedback March 23rd

* Needs good best practice in the absence of rollout sequencing controls that dont always recommend to disable minor and nodes upgrade till eos  
* Lots of GPU/TPU questions, but I dont necessarily have all the expertise there and it is highly dependent on the workload. Also best practices there are complicated since they are likely to change and include not just GKE upgrades but also most likely the host layer. Are questions really upgrades centric or should they also include host maintenance   
* Webhook questions \- get them reviewed by someone else  
* Add specific FAQ on planning

Eval \#1 \- question ok; Clarify that the user wants to trigger the minor version upgrade themselves

Response: 

### \#\#\# General purpose pool

### gcloud container node-pools update general-pool \\

  \--cluster CLUSTER\_NAME \\  
  \--zone us-central1-a \\  
  \--max-surge-upgrade 2 \\  
  \--max-unavailable-upgrade 0

→ Suggest replacing with –max-surge-upgrade 1 and adding a Rationale explaining that the default work but user can increase parallelism for faster upgrades. For instance with 20 nodes in the nodepool and a –max-surge-upgrade 2, GKE can upgrade 10% instead of 5% of nodes concurrently.

I recommend \*\*skip-level upgrades within supported version skew\*\* to minimize total upgrade time: → only suggest skip-level upgrade on nodepool if the customer needs to jump 2 minor versions above the current one( example 1.31-\>1.33). Here they are not since the jump is from 1.32 to 1.33 so dont recommend it

The upgrade plan is correct though it could all be done automatically if the user wishes to do that (triggered during the maintenance window). I’m assuming here that the customer wants to trigger the upgrade themselves. 

Eval \#2 \-  the question would be best formulated with just one channel for both dev and prod environments (Stable or Regular?). That way even when using auto-upgrade they stay on the same minor version. 

Also the user should use rollout sequencing to ensure dev goes before prod, this helps also with patches. 

If they want to initiate the minor upgrade they can have a maintenance exclusion to prevent minor upgrades and initiate the upgrade with the dev cluster when the minor version becomes an auto-upgrade target for that channel (or earlier) and then propagate the minor version to the prod clusters.

Check deprecated API info: in general for deprecated API, check the release notes but also [`https://docs.cloud.google.com/kubernetes-engine/docs/deprecations#deprecations-information`](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations#deprecations-information) `is more specific`  
    
Eval \#13:

gcloud container node-pools update NODE\_POOL\_NAME \\  
    \--cluster CLUSTER\_NAME \\  
    \--zone ZONE \\  
    \--max-surge-upgrade 1 \\  
    \--max-unavailable-upgrade 0

The surge configuration above is the default so it does not need to be set

\#\# Alternative: Dedicated Batch Node Pool Strategy  
→ this solution doesnt work on release channels as it doesnt support per nodepool exclusions. Moreover the gcloud exclusion is wrong; this is a per cluster level configuration. Instead a good alternative would be to use the autoscaled blue green node upgrade strategy with a wait-for-drain period and an annotation on workloads safe-to-evict=false (`https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies#autoscaled-blue-green-upgrade-strategy`  
) 

```
gcloud container node-pools create NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --enable-autoscaling \
    --max-nodes=MAX_NODES \
    --enable-blue-green-upgrade \
    --autoscaled-rollout-policy=[wait-for-drain-duration=WAIT_FOR_DRAIN_DURATIONs]
```

It is also unclear what role the maintenance exclusion plays and why it should be needed

Eval \#38

Eval \#40 

\*\* Per nodepool maintenance exclusions are only available in no channel. Use cluster level exclusion with release channels

\*\*\* What you lose on “Nochannel”  
Note that systematic EoS enforcement is true regardless of channel  
Limited exclusion types. In addition to per-cluster “no upgrades” exclusion, there are per nodepool exclusions

Your upgrade workflow  
3\. \*\*Remove exclusion\*\* when ready to upgrade   
4\. \*\*Re-apply exclusion\*\* after upgrade completes  
→ if you want maximum control, you’re not going to remove your exclusion, user initiated upgrade bypass exclusions, so step 3 & 4 should be removed all together

Review by eval:  
[eval feedback](https://docs.google.com/spreadsheets/d/1kATONdrGnydZFYeEBryWXfRO3o96zd8kxLfvEdaknb0/edit?gid=0&resourcekey=0-kobDUX8RCdg-Yd-osuDprw#gid=0)