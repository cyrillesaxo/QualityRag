/**
 * ICEBERG canonical semantic coordinates, generalized for APX.
 * Source: cyrillesaxo/ICEBERG/docs/ARCHITECTURE.md and
 * packages/core/src/semantic-assurance.js.
 *
 * The taxonomy identifies where meaning may move; it does not establish
 * any security policy, source authority, probability, or admission.
 */
export const CANONICAL_G_TAXONOMY=Object.freeze([
 {code:'G1',name:'Label',meaning:'Names, wording, and lexical identity.'},
 {code:'G2',name:'Node',meaning:'Semantic entity or target identity.'},
 {code:'G3',name:'Boundary',meaning:'Limits, thresholds, validation, and reachable edges.'},
 {code:'G4',name:'Edge',meaning:'Transitions, navigation, and relations between states.'},
 {code:'G5',name:'Operation',meaning:'Actions and effects performed by user or system.'},
 {code:'G6',name:'Perspective',meaning:'Actor, role, access channel, device, or viewpoint.'},
 {code:'G7',name:'Granularity',meaning:'Scale, grouping, pagination, and information density.'},
 {code:'G8',name:'Evidence',meaning:'Confirmation, feedback, assertion, or proof state.'},
 {code:'G9',name:'Prerequisite',meaning:'Preconditions, permissions, validation, and required state.'},
 {code:'G10',name:'Conflict',meaning:'Competing actions, races, duplicates, and contradictory states.'},
 {code:'G11',name:'Temporal',meaning:'Timing, retry, expiry, ordering, interruption, and freshness.'},
 {code:'G12',name:'Authority',meaning:'Authoritative source, role delegation, backend ownership, and approval.'},
] as const)
export type CanonicalGCode=typeof CANONICAL_G_TAXONOMY[number]['code']
