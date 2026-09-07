class Uncle < Formula
  desc "Terminal UI and launcher for governed-CI agent workflows"
  homepage "https://github.com/unclehq/uncle"
  license "MIT"
  head "https://github.com/unclehq/uncle.git", branch: "main"

  depends_on "gh"
  depends_on "git"
  depends_on "jq"
  depends_on "python@3.13"
  uses_from_macos "curl"

  def install
    libexec.install "uncle", "uncle_tui.py", "scripts", "prompts", "lib", "OUTPUT_RULES.md"
    prefix.install_metafiles

    # The launcher shells out to bare `python3` for the TUI; python@3.13 keeps
    # its unversioned python3 symlink in libexec/bin, off PATH by default.
    (bin/"uncle").write_env_script libexec/"uncle",
                                  PATH: "#{formula_opt_libexec("python@3.13")}/bin:$PATH"
  end

  def caveats
    <<~EOS
      Run `uncle` from any directory. The first time you run it in a project,
      it opens the Configure screen to set up the project.

      Workflow stages run through an external agent CLI (cline, claude, kimi,
      or codex); install and configure at least one before starting a workflow.
    EOS
  end

  test do
    assert_path_exists libexec/"uncle_tui.py"
    assert_predicate libexec/"scripts", :directory?

    assert_match "Usage: uncle", shell_output("#{bin}/uncle --help")
    assert_match "Unknown argument", shell_output("#{bin}/uncle --bogus 2>&1", 1)

    (testpath/".uncle/workspace/metrics").mkpath
    (testpath/".uncle/workspace/metrics/sample.json").write <<~JSON
      {"kind":"agent","stage":"requirements","elapsed_seconds":3,"input_tokens":10,"output_tokens":5,"reported_total_tokens":15}
    JSON
    assert_match "requirements", shell_output("#{bin}/uncle --performance")
  end
end
