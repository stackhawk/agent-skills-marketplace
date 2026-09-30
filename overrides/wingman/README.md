# StackHawk Wingman

Wingman installs the default StackHawk skill set together: HawkScan scanning, StackHawk platform reporting, seed data setup, and scan optimization. Its Claude Code manifest declares those four plugins as dependencies, so one Wingman install brings in the four skills from this marketplace. Wingman intentionally has no skill of its own. Each dependency comes from the same pinned `stackhawk/agent-skills` release.

HawkScan actions use the `hawk` CLI and may connect to your StackHawk account. They can scan an application, query findings, or write configuration and seed artifacts in a repository when the relevant skill is invoked. Review each skill's instructions and the [Claude Code installation guide](https://docs.stackhawk.com/ai-security/agent-skills/claude-code/) before use. [StackHawk support](https://docs.stackhawk.com/support/) can help with setup.

The plugin manifest contains the release version and links to StackHawk's privacy policy and terms.
