class Uncle < Formula
  include Language::Python::Virtualenv
  desc "Terminal UI and launcher for governed-CI agent workflows"
  homepage "https://github.com/unclehq/uncle"
  license "MIT"
  head "https://github.com/unclehq/uncle.git", branch: "main"

  depends_on "gh"
  depends_on "git"
  depends_on "jq"
  depends_on "python@3.13"
  uses_from_macos "curl"

  resource "pytest" do
    url "https://files.pythonhosted.org/packages/e4/47/b9efed96c114afcfa3c9d3fe98a76a1d14c74a9e266d397cf6eb64be5e01/pytest-9.1.1.tar.gz"
    sha256 "1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6d71f0ffda5fe313"
  end

  resource "iniconfig" do
    url "https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz"
    sha256 "c76315c77db068650d49c5b56314774a7804df16fee4402c1f19d6d15d8c4730"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/d7/f1/e7a6dd94a8d4a5626c03e4e99c87f241ba9e350cd9e6d75123f992427270/packaging-26.2.tar.gz"
    sha256 "ff452ff5a3e828ce110190feff1178bb1f2ea2281fa2075aadb987c2fb221661"
  end

  resource "pluggy" do
    url "https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz"
    sha256 "7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz"
    sha256 "6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f"
  end

  resource "execnet" do
    url "https://files.pythonhosted.org/packages/bf/89/780e11f9588d9e7128a3f87788354c7946a9cbb1401ad38a48c4db9a4f07/execnet-2.1.2.tar.gz"
    sha256 "63d83bfdd9a23e35b9c6a3261412324f964c2ec8dcd8d3c6916ee9373e0befcd"
  end

  resource "pytest-xdist" do
    url "https://files.pythonhosted.org/packages/78/b4/439b179d1ff526791eb921115fca8e44e596a13efeda518b9d845a619450/pytest_xdist-3.8.0.tar.gz"
    sha256 "7e578125ec9bc6050861aa93f2d59f1d8d085595d6551c2c90b6f4fad8d3a9f1"
  end

  def install
    venv = virtualenv_create(libexec/"venv", Formula["python@3.13"].opt_bin/"python3.13")
    resources.each { |r| venv.pip_install r }
    libexec.install "uncle", "uncle_tui.py", "scripts", "prompts", "lib", "OUTPUT_RULES.md"
    prefix.install_metafiles
    prefix.install "uncle.png"

    # Use the private environment for the TUI and stage checks so bare
    # python3 can import pytest and xdist as well as run Uncle.
    #
    # opt_libexec, not libexec: the versioned keg path is deleted and recreated
    # by `brew reinstall`, and a workflow can run for hours. Launching from the
    # versioned path meant an upgrade mid-run pulled the scripts out from under
    # a live driver, which then failed on files that no longer existed. The opt
    # symlink always resolves to the installed version instead.
    (bin/"uncle").write_env_script opt_libexec/"uncle",
                                  PATH: "#{opt_libexec}/venv/bin:$PATH"
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
    system libexec/"venv/bin/python", "-c", "import pytest, xdist"
    assert_path_exists libexec/"uncle_tui.py"
    assert_predicate libexec/"scripts", :directory?

    assert_match "Usage: uncle", shell_output("#{bin}/uncle --help")
    assert_match "Unknown argument", shell_output("#{bin}/uncle --bogus 2>&1", 1)

    (testpath/".uncle/workflow/metrics").mkpath
    (testpath/".uncle/workflow/metrics/sample.json").write <<~JSON
      {"kind":"agent","stage":"requirements","elapsed_seconds":3,"input_tokens":10,"output_tokens":5,"reported_total_tokens":15}
    JSON
    assert_match "requirements", shell_output("#{bin}/uncle --performance")
  end
end
