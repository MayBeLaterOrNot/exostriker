import os
import subprocess
import sys
from pathlib import Path
import shutil


def get_python_version():
    """Return the current Python executable path (e.g., /usr/bin/python3.13)."""
    return sys.executable  # Automatically detects the running Python version


def get_python_so_filename():
    """
    Generate the expected .so or .pyd filename for the current Python version.
    """
    python_version = f"{sys.version_info.major}{sys.version_info.minor}"
    if sys.platform == "win32":
        return f"swift.cp{python_version}-win_amd64.pyd"  # Windows filename format
    else:
        return f"swift.cpython-{python_version}-x86_64-linux-gnu.so"  # Linux/macOS filename format

def compile_fortran(source_dir, output_lib):
    """
    Compiles Fortran files into object files and creates a static library.
    Works on macOS, Linux, and Windows (if gfortran is installed).
    """
    source_dir = Path(source_dir)  # Ensure source_dir is a Path object
    output_lib = Path(output_lib)  # Ensure output_lib is a Path object

    # **Skip compilation if library already exists**
    if output_lib.exists():
        print(f"Skipping Fortran compilation: {output_lib} already exists.")
        return

    object_files = []

    # Compiler flags from original make files
    FFLAGS = ["-O3", "-c"]  # Optimization and compilation flag
    CPPFLAGS = ["-D_OPEN_POSITION", "-D_RECUR_SUB"]  # Preprocessor flags

    # Recursively find and compile .f and .F Fortran files
    for fortran_file in list(source_dir.rglob("*.f")) + list(source_dir.rglob("*.F")):
        obj_file = fortran_file.with_suffix(".o")
        print(f"Compiling {fortran_file} -> {obj_file}")

        # Use -cpp for preprocessing if the file has a .F extension
        extra_flags = ["-cpp"] if fortran_file.suffix.lower() == ".F" else []

        # Compile using gfortran with necessary flags
        compile_cmd = ["gfortran", "-c", "-frecursive"] + FFLAGS + CPPFLAGS + extra_flags + [str(fortran_file), "-o", str(obj_file)]
        result = subprocess.run(compile_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Skipping {fortran_file} due to compilation error:", result.stderr)
            continue  # Skip file and move to the next one

        object_files.append(str(obj_file))

    if not object_files:
        print("No Fortran files compiled successfully.")
        return

    # Create static library
    print(f"Creating static library {output_lib}")

    if sys.platform == "win32":
        # Use Microsoft's lib.exe for Windows
        ar_cmd = ["lib", f"/OUT:{output_lib}"] + object_files
    else:
        # Use Unix-based ar command
        ar_cmd = ["ar", "rsv", str(output_lib)] + object_files

    result = subprocess.run(ar_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Error creating library:", result.stderr)
        sys.exit(1)

    # Run ranlib (optional, mainly for macOS compatibility)
    if sys.platform != "win32":
        subprocess.run(["ranlib", str(output_lib)], capture_output=True, text=True)

    print("Compilation successful!")


def compile_python_extension():
    """
    Compiles the Python extension using f2py (for Python 3.10-3.12) or Meson (for Python 3.13+).
    """
    extension_name = "swift"
    source_directory = Path("source") / "swift_j"
    lib_swift_dir = Path("lib") / "swift"  # Destination directory    

    swift_source = lib_swift_dir / "swift.f95"  # Original source location
    static_lib = lib_swift_dir / ("libswift.a" if sys.platform != "win32" else "libswift.lib")
    build_dir = lib_swift_dir / "bdir"  # Build directory (outside `lib/swift/`)

    # **Step 1: Check if the correct version of Python extension is already compiled**
    expected_so_file = lib_swift_dir / get_python_so_filename()

    if expected_so_file.exists():
        print(f"Skipping Python extension compilation: {expected_so_file} already exists.")
        return

    # **Step 2: Ensure `libswift.a` exists (if missing, recompile Fortran)**
    if not static_lib.exists():
        print(f"Error: The Fortran library {static_lib} was not created!")
        compile_fortran(source_directory, static_lib)
        #sys.exit(1)

    # Store the original working directory
    original_dir = Path.cwd()

    #print(original_dir, swift_source,static_lib, lib_swift_dir,build_dir)

    # **Step 3: Change directory to `lib/swift/`**
    #os.chdir(lib_swift_dir)
    #current_dir = Path.cwd()


    if sys.version_info.major == 4 and sys.version_info.minor >= 14:  # junk only for tests!
        # **Use Meson for Python 3.13+**
        print("Using Meson to compile Python extension for Python 3.13+...")

        os.system("rm %s"%build_dir)
        # Ensure the build directory exists
        if not build_dir.exists():
            build_dir.mkdir(parents=True, exist_ok=True)

        # Run Meson setup only if it's not already configured
        meson_config_file = build_dir / "meson-private" / "coredata.dat"
        if not meson_config_file.exists():
            print("Setting up Meson for the first time...")
            setup_cmd = ["meson", "setup", str(build_dir), str(lib_swift_dir)]
        else:
            print("Reconfiguring existing Meson build...")
            setup_cmd = ["meson", "setup", "--reconfigure", str(build_dir)]

        result = subprocess.run(setup_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print("Error setting up Meson:")
            print(result.stderr)
            sys.exit(1)

        # Check if Meson actually created build.ninja
        build_ninja_file = build_dir / "build.ninja"
        if not build_ninja_file.exists():
            print("Error: Meson did not generate 'build.ninja'. Check meson.build for issues.")
            sys.exit(1)

        # Compile using Ninja
        build_cmd = ["ninja", "-C", str(build_dir)]
        result = subprocess.run(build_cmd, capture_output=True, text=True)

    elif sys.version_info.major == 3 and sys.version_info.minor >= 13:
    
    
        os.chdir(lib_swift_dir)
        current_dir = Path.cwd()
        # **Use F2PY for Python 3.10-3.12**
        print("Using F2PY to compile Python extension...")
        recur = "-fmax-stack-var-size=2147483646" if "win" in sys.platform[:3] else "-fmax-stack-var-size=2147483646"
        vers = f"{sys.version_info.major}.{sys.version_info.minor}"
 
        if "win" in sys.platform[:3]:
            compile_cmd = f'python{vers} -m numpy.f2py -c --opt="-O3 -std=legacy {recur}" -m swift swift.f95 -L{current_dir} -lswift --extra-link-args="{current_dir}/libswift.lib" --build-dir bdir -I{current_dir}'           
          
        else:
            compile_cmd = f'python{vers} -m numpy.f2py -c --opt="-O3 -std=legacy {recur}" -m swift swift.f95 -L{current_dir} -lswift --extra-link-args="{current_dir}/libswift.a" --build-dir bdir -I{current_dir}'

        result = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True)
        # **Step 5: Change back to the original directory after compilation**
        os.chdir(original_dir)
 
    else:
    
        os.chdir(lib_swift_dir)
        current_dir = Path.cwd()
        # **Use F2PY for Python 3.10-3.12**
        print("Using F2PY to compile Python extension...")
        recur = "-fmax-stack-var-size=2147483646" if "win" in sys.platform[:3] else "-fmax-stack-var-size=2147483646"
        vers = f"{sys.version_info.major}.{sys.version_info.minor}"

        if "win" in sys.platform[:3]:
            compile_cmd = f'python{vers} -m numpy.f2py -c --opt="-O3 -std=legacy {recur}" -m swift swift.f95 libswift.lib --build-dir bdir -I{current_dir}'
        else:
            compile_cmd = f'python{vers} -m numpy.f2py -c --opt="-O3 -std=legacy {recur}" -m swift swift.f95 libswift.a --build-dir bdir -I{current_dir}'
            
 

        result = subprocess.run(compile_cmd, shell=True, capture_output=True, text=True)
        # **Step 5: Change back to the original directory after compilation**
        os.chdir(original_dir)
        
    if result.returncode != 0:
        print("Error compiling Python extension:", result.stderr)
        sys.exit(1)


    print(f"Python extension compiled successfully! ({expected_so_file})")


if __name__ == "__main__":
    compile_python_extension()

