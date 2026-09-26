# StackHawk Data Seed

This plugin helps prepare repeatable seed data so HawkScan can exercise authenticated application paths that need existing users or records. Its skill reads the target repository, asks HawkScan's local seed preflight for storage and route information, then writes a seed manifest and reviewed artifacts in that target repository. It does not start services or run the generated seed steps for you.

The workflow uses the `hawk` CLI and may create SQL, HTTP, gRPC, MongoDB, or shell seed steps depending on the application. Review the output and credentials handoff before applying it. See the [Claude Code installation guide](https://docs.stackhawk.com/ai-security/agent-skills/claude-code/) and [StackHawk support](https://docs.stackhawk.com/support/) for setup and help.

This marketplace copy comes from the pinned `stackhawk/agent-skills` release. The plugin manifest contains the release version and links to StackHawk's privacy policy and terms.
