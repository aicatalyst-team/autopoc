# 11. Refactor to OpenCode Agent with Skills

Date: 2026-05

## Status

Accepted

## Context

AutoPoC originally used LangGraph to orchestrate multiple ReAct agents in a complex state graph with retry loops and parallel execution. While functional, this approach had several limitations:

- **Complexity**: Managing multiple agent states, routing logic, and state merge semantics
- **Debugging difficulty**: Complex graph execution made troubleshooting challenging  
- **Development overhead**: Each new feature required agent code, routing logic, and state management
- **Context management**: Token overflow handling across multiple agent conversations
- **Deployment complexity**: LangGraph runtime dependencies and checkpoint management

## Decision

Refactor AutoPoC from a LangGraph multi-agent system to a single OpenCode agent following detailed skill instructions.

**New Architecture:**
- **Single Agent**: OpenCode is the sole intelligent agent
- **Skill-driven**: Complex logic encoded in markdown skill instructions
- **Progressive State**: YAML state file tracks progress through phases
- **Containerized Execution**: Runs in Kubernetes pods with OpenCode runtime
- **11-Phase Pipeline**: Sequential execution with built-in retry logic

## Alternatives Considered

- **Keep LangGraph**: Continue with the existing multi-agent approach
  - Rejected: Complexity and debugging challenges outweigh benefits
- **Custom Python orchestrator**: Build a simpler state machine
  - Rejected: Would lose the benefits of having an intelligent agent handle edge cases
- **Other agent frameworks**: Crew AI, AutoGen, etc.
  - Rejected: Still require managing multiple agents and complex state

## Consequences

### Positive
- **Simplified Architecture**: Single agent eliminates routing complexity and state conflicts
- **Better Error Handling**: OpenCode can reason about failures and adapt instructions dynamically
- **Easier Development**: New features added via skill instructions rather than agent code
- **Improved Debugging**: Direct access to OpenCode's reasoning and execution logs
- **Containerized Deployment**: Runs in K8s pods without complex runtime dependencies
- **Skills Reusability**: Skills can be shared across different OpenCode deployments

### Negative
- **OpenCode Dependency**: Requires OpenCode runtime and licensing
- **Skill Complexity**: Complex instructions must be encoded in markdown rather than code
- **Sequential Execution**: Loss of parallel execution (poc_plan || fork)
- **State Management**: Manual YAML file management vs. automatic TypedDict updates

### Migration Impact
- **Deprecated Components**: LangGraph agents, routing functions, state merging logic
- **Retained Components**: Python tools, templates, evaluation strategies
- **New Components**: OpenCode skills, YAML state management, container deployment

## Implementation

The refactor is implemented in phases:

1. **Design Phase**: Create skill instructions and reference files
2. **Tool Adaptation**: Convert LangGraph tools to standalone CLI scripts
3. **Container Updates**: Add OpenCode runtime to container images
4. **Deployment Updates**: Kubernetes manifests for OpenCode execution
5. **Testing**: Update test suite for skill-based architecture
6. **Cleanup**: Remove deprecated LangGraph components

This change represents a fundamental shift from complex multi-agent orchestration to simplified single-agent execution with skill-driven behavior.