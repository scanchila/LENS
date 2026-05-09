"""Lens-specific agent definitions.

Each lens is a distinct AgentDefinition (or a tightly-related cluster:
proposer + critic-template) encoding one method for surfacing
non-obvious problems from the user's data.

Phase 0 ships only ``cross_domain_transfer``. Subsequent phases add:
  * counterfactual_perturbation
  * contradiction_surfacing
  * distance_from_focus
  * causal_exposure
  * compression_novelty
  * outsider_perspective
"""
