# DTN AI Routing — Stage 5 Label Generation Specification (Audited)

## 1. Objective and Problem Formulation
At simulation time $t$, node $u$ holds packet $P$ and encounters peer $v$. The node must choose between:
- Action $a = 1$: **Forward** (Replicate bundle to peer $v$).
- Action $a = 0$: **Hold / Wait** (Retain bundle in buffer; wait for alternative encounters).

## 2. Simulation-Derived Teacher Label Definition
The binary target `target_should_forward` is defined using the offline Time-Dependent A* shortest path oracle:

$$\text{target\_should\_forward} = \begin{cases} 
0, & \text{if } t + \Delta t_{\text{transfer}} > t_{\text{contact\_end}} \text{ (physically truncated transfer)} \\
1, & \text{if } v == P.\text{destination} \text{ (direct delivery to destination)} \\
1, & \text{if } (u \to v)_t \text{ is the scheduled first hop on } P\text{'s optimal temporal A* path} \\
0, & \text{otherwise (inferior or redundant forwarding opportunity)}
\end{cases}$$

## 3. Mathematical Clarification of the Stage 5 Audit
In the preliminary Stage 5 implementation, the teacher tested $T_v < T_u$, where $T_u$ was the arrival time from sender $u$ departing at $t$. Because the search space from $u$ at $t$ already includes the forwarding transfer $(u \to v)$ at $t$, $T_u \le T_v$ was mathematically guaranteed for all encounters, causing $T_v < T_u$ to evaluate to False on 100% of non-destination encounters.
The corrected formulation directly inspects whether the contact $(u \to v)_t$ lies on the global earliest-arrival time-dependent route planned by the Time-Dependent A* oracle, correctly identifying both direct deliveries and optimal intermediate relay opportunities.
