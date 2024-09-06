import argparse
import os
from pathlib import Path
from contextlib import chdir
import subprocess
import ast

# Globals
TUDATPY_ROOT = Path("tudatpy/src/tudatpy").absolute()
STUBS_ROOT = Path("tudatpy/src/tudatpy-stubs").absolute()
CONDA_PREFIX = os.environ["CONDA_PREFIX"]

# Define argument parser
parser = argparse.ArgumentParser(
    prog="build.py",
    description="Build Tudat, TudatPy and generate stubs",
)

parser.add_argument(
    "-j", metavar="<cores>", type=int, default=1, help="Number of processors to use"
)
parser.add_argument(
    "-c",
    "--clean",
    action="store_true",
    help="Clean after build",
)
parser.add_argument(
    "--build-dir",
    metavar="<path>",
    type=str,
    default="build",
    help="Build directory",
)
parser.add_argument(
    "--build-type",
    metavar="<type>",
    default="Release",
    help="Build type: Release, Debug",
)
parser.add_argument(
    "--no-tests",
    dest="tests",
    action="store_false",
    help="Build Tudat tests",
)
parser.add_argument(
    "--no-sofa",
    dest="sofa",
    action="store_false",
    help="Build without SOFA",
)
parser.add_argument(
    "--no-nrlmsise00",
    dest="nrlmsise00",
    action="store_false",
    help="Build without NRLMSISE00",
)
parser.add_argument(
    "--json",
    dest="json",
    action="store_true",
    help="Build with JSON interface",
)
parser.add_argument(
    "--pagmo",
    action="store_true",
    help="Build with PaGMO",
)
parser.add_argument(
    "--extended-precision",
    action="store_true",
    help="Build with extended precision propagation tools",
)

# Choose what to compile
parser.add_argument(
    "--no-compile",
    dest="compile",
    action="store_false",
    help="Skip compilation of tudat and tudatpy",
)
parser.add_argument(
    "--clean-stubs",
    dest="clean_stubs",
    action="store_true",
    help="Generate TudatPy stubs from scratch",
)
parser.add_argument(
    "--cxx-standard",
    metavar="<standard>",
    default="14",
    help="C++ standard",
)


# Stub generation
class StubGenerator:

    def __init__(self, clean: bool = False) -> None:
        self.clean = clean
        return None

    def generate_stubs(self, source_dir: Path) -> None:
        """Generates stubs for a package.

        :param source_dir: Path to base directory of the package
        """

        # Generate stub for main init file
        StubGenerator._generate_init_stub(source_dir)

        # Generate stubs for C++ extensions
        for extension in source_dir.rglob("*.so"):

            # Skip extension if stub exists and clean flag is not set
            extension_stub_path = STUBS_ROOT / extension.relative_to(
                TUDATPY_ROOT
            ).with_suffix("").with_suffix(".pyi")
            if extension_stub_path.exists() and not self.clean:
                continue

            # Generate stub
            extension_import_path = f"tudatpy.{str(extension.relative_to(TUDATPY_ROOT).with_suffix('').with_suffix('')).replace('/', '.')}"
            print(f"Generating stubs for {extension_import_path}...")
            outcome = subprocess.run(
                [
                    "pybind11-stubgen",
                    extension_import_path,
                    "-o",
                    ".",
                    "--root-suffix=-stubs",
                    "--numpy-array-remove-parameters",
                ]
            )
            if outcome.returncode:
                exit(outcome.returncode)

            # Clean autogenerated stub
            self._clean_autogenerated_stub(extension_import_path)

        # Loop over submodules
        for submodule in source_dir.iterdir():
            if submodule.is_dir() and (submodule / "__init__.py").exists():
                self._generate_module_stubs(submodule)

        return None

    def _generate_module_stubs(self, module_path: Path) -> None:
        """Generates stubs for a module

        :param module_path: Path to module directory
        """

        # Loop over submodules
        for submodule in module_path.iterdir():
            if submodule.is_dir() and (submodule / "__init__.py").exists():
                self._generate_module_stubs(submodule)

        # Define import path and display info
        import_path = (
            f'tudatpy.{str(module_path.relative_to(TUDATPY_ROOT)).replace("/", ".")}'
        )

        # Generate __init__ stub
        StubGenerator._generate_init_stub(module_path)

        # Find python scripts included in __init__
        with open(module_path / "__init__.py") as _f:
            _content = ast.parse(_f.read())

        _python_modules = []
        for _statement in _content.body:
            if isinstance(_statement, ast.ImportFrom):
                if "expose" in str(_statement.module) or _statement.module is None:
                    continue
                _python_modules.append(_statement.module)

        # Generate stubs for python scripts
        for _python_module in _python_modules:

            # Skip extension if stub exists and clean flag is not set
            script_import_path = f"{import_path}.{_python_module}"
            script_stub_path = STUBS_ROOT / Path(
                "/".join(script_import_path.split(".")[1:])
            ).with_suffix(".pyi")
            if script_stub_path.exists() and not self.clean:
                continue
            print(f"Generating stub for {script_import_path}...")
            outcome = subprocess.run(
                [
                    "pybind11-stubgen",
                    script_import_path,
                    "-o",
                    ".",
                    "--root-suffix=-stubs",
                    "--numpy-array-remove-parameters",
                ]
            )
            if outcome.returncode:
                exit(outcome.returncode)

            # Clean autogenerated stub
            self._clean_autogenerated_stub(script_import_path)

        return None

    @staticmethod
    def _generate_init_stub(module_path: Path) -> None:
        """Generates stub for __init__ file

        :param module_path: Path to module directory
        """
        # Define path to stub file
        stub_path = module_path.relative_to(TUDATPY_ROOT)
        stub_path = STUBS_ROOT / f"{stub_path}/__init__.pyi"

        # Parse __init__ file
        with open(module_path / "__init__.py") as src:
            content = ast.parse(src.read())

        import_statements = []
        other_statements = []
        for statement in content.body:

            if isinstance(statement, ast.Import):
                raise NotImplementedError("Import statement not supported yet")
            elif isinstance(statement, ast.ImportFrom):
                if statement.names[0].name == "*":
                    assert statement.module is not None
                    with (
                        stub_path.parent / f"{statement.module.replace('.', '/')}.pyi"
                    ).open() as f:
                        _data = ast.parse(f.read())
                        for _statement in _data.body:
                            if (
                                isinstance(_statement, ast.Assign)
                                and len(_statement.targets) == 1
                                and isinstance(_statement.targets[0], ast.Name)
                                and _statement.targets[0].id == "__all__"
                            ):
                                assert isinstance(_statement.value, ast.List)
                                _equivalent_import = ast.ImportFrom(
                                    module=statement.module,
                                    level=statement.level,
                                    names=[
                                        ast.alias(name=elt.value)  # type: ignore
                                        for elt in _statement.value.elts
                                    ],
                                )
                                import_statements.append(_equivalent_import)
                else:
                    import_statements.append(statement)

            elif isinstance(statement, ast.Assign):
                if statement.targets[0].id == "__all__":  # type: ignore
                    continue
                other_statements.append(statement)

        # Generate import statement for submodules
        submodule_list = []
        for submodule in module_path.iterdir():
            if submodule.is_dir() and (submodule / "__init__.py").exists():
                submodule_list.append(submodule)

        if len(submodule_list) > 0:
            import_submodules_statement = ast.ImportFrom(
                module="",
                level=1,
                names=[ast.alias(name=submodule.name) for submodule in submodule_list],
            )
            import_statements.append(import_submodules_statement)

        # Generate __all__ statement
        if len(import_statements) == 0:
            all_statement = ast.parse("__all__ = []").body[0]
        else:
            all_statement = ast.parse(
                "__all__ = ["
                + ", ".join(
                    [
                        f"'{alias.name}'"
                        for statement in import_statements
                        for alias in statement.names
                    ]
                )
                + "]"
            ).body[0]

        # Generate __init__.pyi
        init_contents = import_statements + other_statements + [all_statement]
        init_module = ast.Module(body=init_contents, type_ignores=[])
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stub_path, "w") as f:
            f.write(ast.unparse(init_module))

        return None

    @staticmethod
    def _clean_autogenerated_stub(import_path: str) -> None:
        """Cleans autogenerated stub

        :param import_path: Import path to module
        """

        stub_path = STUBS_ROOT / Path("/".join(import_path.split(".")[1:])).with_suffix(
            ".pyi"
        )

        with open(stub_path) as f:
            content = ast.parse(f.read())

        includes_typing = False
        for statement in content.body:

            if isinstance(statement, ast.ImportFrom):
                if statement.module == "__future__":
                    content.body.remove(statement)

            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    if alias.name == "typing":
                        includes_typing = True
                        break

        if not includes_typing:
            content.body.insert(0, ast.Import([ast.alias("typing")]))

        with open(stub_path, "w") as f:
            f.write(ast.unparse(content))

        return None


def generate_init_stub(module_path: Path) -> None:

    # Define path to stub file
    stub_path = module_path.relative_to(TUDATPY_ROOT)
    stub_path = STUBS_ROOT / f"{stub_path}/__init__.pyi"

    # Parse __init__ file
    with open(module_path / "__init__.py") as src:
        content = ast.parse(src.read())

    import_statements = []
    other_statements = []
    for statement in content.body:

        if isinstance(statement, ast.Import):
            raise NotImplementedError("Import statement not supported yet")
        elif isinstance(statement, ast.ImportFrom):
            if statement.names[0].name == "*":
                assert statement.module is not None
                with (stub_path.parent / f"{statement.module}.pyi").open() as f:
                    _data = ast.parse(f.read())
                    for _statement in _data.body:
                        if (
                            isinstance(_statement, ast.Assign)
                            and len(_statement.targets) == 1
                            and isinstance(_statement.targets[0], ast.Name)
                            and _statement.targets[0].id == "__all__"
                        ):
                            assert isinstance(_statement.value, ast.List)
                            _equivalent_import = ast.ImportFrom(
                                module=statement.module,
                                level=statement.level,
                                names=[
                                    ast.alias(name=elt.value)  # type: ignore
                                    for elt in _statement.value.elts
                                ],
                            )
                            import_statements.append(_equivalent_import)
            else:
                import_statements.append(statement)

        elif isinstance(statement, ast.Assign):
            if statement.targets[0].id == "__all__":  # type: ignore
                continue
            other_statements.append(statement)

    # Generate import statement for submodules
    submodule_list = []
    for submodule in module_path.iterdir():
        if submodule.is_dir() and (submodule / "__init__.py").exists():
            submodule_list.append(submodule)

    if len(submodule_list) > 0:
        import_submodules_statement = ast.ImportFrom(
            module="",
            level=1,
            names=[ast.alias(name=submodule.name) for submodule in submodule_list],
        )
        import_statements.append(import_submodules_statement)

    # Generate __all__ statement
    if len(import_statements) == 0:
        all_statement = ast.parse("__all__ = []").body[0]
    else:
        all_statement = ast.parse(
            "__all__ = ["
            + ", ".join(
                [
                    f"'{alias.name}'"
                    for statement in import_statements
                    for alias in statement.names
                ]
            )
            + "]"
        ).body[0]

    # Generate __init__.pyi
    init_contents = import_statements + other_statements + [all_statement]
    init_module = ast.Module(body=init_contents, type_ignores=[])
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stub_path, "w") as f:
        f.write(ast.unparse(init_module))

    return None

    import_statements = []
    init_content = []
    all_statement = None
    for statement in content.body:

        if isinstance(statement, ast.Import):
            raise NotImplementedError("Import statement not supported yet")

        elif isinstance(statement, ast.ImportFrom):
            import_statements.append(statement)

        elif isinstance(statement, ast.Assign):
            if not len(statement.targets) == 1:
                continue
            if not isinstance(statement.targets[0], ast.Name):
                continue
            if not statement.targets[0].id == "__all__":
                continue

            all_statement = statement
            break

        else:
            print(type(statement), statement._fields)

    # Add import statements to init contents
    for statement in import_statements:
        init_content.append(statement)

    # Import submodules
    submodule_list = []
    for submodule in module_path.iterdir():
        if submodule.is_dir() and (submodule / "__init__.py").exists():
            submodule_list.append(submodule)

    if len(submodule_list) > 0:
        import_submodules_statement = ast.ImportFrom(
            module="",
            level=1,
            names=[ast.alias(name=submodule.name) for submodule in submodule_list],
        )
        init_content.append(import_submodules_statement)

    # Add __all__ statement to init contents
    if all_statement is not None:
        assert isinstance(all_statement.value, ast.List)
        all_statement.value.elts.extend(
            [ast.Constant(submodule.name) for submodule in submodule_list]
        )
    else:
        all_statement = ast.parse(
            "__all__ = ["
            + ", ".join([f"'{submodule.name}'" for submodule in submodule_list])
            + "]"
        ).body[0]

    init_content.append(all_statement)

    # Generate __init__.pyi
    init_module = ast.Module(body=init_content, type_ignores=[])
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stub_path, "w") as f:
        f.write(ast.unparse(init_module))

    return None


def clean_autogenerated_stub(import_path: str) -> None:

    stub_path = STUBS_ROOT / Path("/".join(import_path.split(".")[1:])).with_suffix(
        ".pyi"
    )

    with open(stub_path) as f:
        content = ast.parse(f.read())

    includes_typing = False
    for statement in content.body:

        if isinstance(statement, ast.ImportFrom):
            if statement.module == "__future__":
                content.body.remove(statement)

        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "typing":
                    includes_typing = True
                    break

    if not includes_typing:
        content.body.insert(0, ast.Import([ast.alias("typing")]))

    with open(stub_path, "w") as f:
        f.write(ast.unparse(content))

    return None


def generate_module_stubs(module_path: Path) -> None:

    if not (module_path / "__init__.py").exists():
        return None

    import_path = (
        f'tudatpy.{str(module_path.relative_to(TUDATPY_ROOT)).replace("/", ".")}'
    )

    print(f"Generating stubs for {import_path}...")

    # Check if init file is empty
    empty_init = False
    with open(module_path / "__init__.py") as f:
        if f.read().strip() == "":
            empty_init = True

    if not empty_init:
        # Generate stubs for extensions
        for extension in module_path.glob("*.so"):
            extension_import_path = f"{import_path}.{extension.name.split('.')[0]}"
            outcome = subprocess.run(
                [
                    "pybind11-stubgen",
                    extension_import_path,
                    "-o",
                    ".",
                    "--root-suffix=-stubs",
                    "--numpy-array-remove-parameters",
                ]
            )
            if outcome.returncode:
                exit(outcome.returncode)

            # Clean autogenerated stub
            clean_autogenerated_stub(extension_import_path)

        # Generate stubs for python scripts
        for script in module_path.glob("*.py"):
            if script.name != "__init__.py":
                script_import_path = f"{import_path}.{script.stem}"
                # print(script_import_path)
                outcome = subprocess.run(
                    [
                        "pybind11-stubgen",
                        script_import_path,
                        "-o",
                        ".",
                        "--root-suffix=-stubs",
                        "--numpy-array-remove-parameters",
                    ]
                )
                if outcome.returncode:
                    exit(outcome.returncode)

                # Clean autogenerated stub
                clean_autogenerated_stub(script_import_path)

    # Generate stub for __init__ file
    if (module_path / "__init__.py").exists():
        generate_init_stub(module_path)

    return None


def generate_stubs(module_path: Path) -> None:

    generate_module_stubs(module_path)

    for submodule in module_path.iterdir():
        if submodule.is_dir() and (submodule / "__init__.py").exists():
            generate_stubs(submodule)


if __name__ == "__main__":

    # Retrieve command line arguments
    args = parser.parse_args()

    # Ensure build directory exists
    build_dir = Path(args.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    # Build
    if args.compile:
        with chdir(build_dir):
            outcome = subprocess.run(
                [
                    "cmake",
                    f"-DCMAKE_PREFIX_PATH={CONDA_PREFIX}",
                    f"-DCMAKE_INSTALL_PREFIX={CONDA_PREFIX}",
                    f"-DCMAKE_CXX_STANDARD={args.cxx_standard}",
                    "-DBoost_NO_BOOST_CMAKE=ON",
                    f"-DCMAKE_BUILD_TYPE={args.build_type}",
                    f"-DTUDAT_BUILD_TESTS={args.tests}",
                    f"-DTUDAT_BUILD_WITH_SOFA_INTERFACE={args.sofa}",
                    f"-DTUDAT_BUILD_WITH_NRLMSISE00={args.nrlmsise00}",
                    f"-DTUDAT_BUILD_WITH_PAGMO={args.pagmo}",
                    f"-DTUDAT_BUILD_WITH_JSON_INTERFACE={args.json}",
                    f"-DTUDAT_BUILD_WITH_EXTENDED_PRECISION_PROPAGATION_TOOLS={args.extended_precision}",
                    "..",
                ]
            )
            if outcome.returncode:
                exit(outcome.returncode)

            build_command = ["cmake", "--build", "."]
            if args.clean:
                build_command.append("--target")
                build_command.append("clean")
            build_command.append(f"-j{args.j}")
            outcome = subprocess.run(build_command)
            if outcome.returncode:
                exit(outcome.returncode)

    # Post-process tudatpy stubs
    with chdir("tudatpy/src"):
        stub_generator = StubGenerator(clean=args.clean_stubs)
        stub_generator.generate_stubs(TUDATPY_ROOT)
