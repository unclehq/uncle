class Uncle < Formula
  desc "Terminal UI and launcher for governed-CI agent workflows"
  homepage "https://github.com/unclehq/uncle"
  license "MIT"
  head "https://github.com/unclehq/uncle.git", branch: "main"

  depends_on "python@3.13"

  def install
    libexec.install "uncle"
    libexec.install "uncle_tui.py"
    libexec.install "scripts"
    libexec.install "prompts"
    libexec.install "lib"
    libexec.install "OUTPUT_RULES.md"

    bin.install_symlink libexec/"uncle"
  end

  def caveats
    <<~EOS
      Run `uncle` from any directory. The first time you run it in a project,
      it opens the Configure screen to set up the project.
    EOS
  end

  test do
    system "#{bin}/uncle", "--help"
  end
end
