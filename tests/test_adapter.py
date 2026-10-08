"""Protocol tests using invented numbers; no research structures or QM jobs."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from turbomole_namd import adapter as qm


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def write(self, name, text):
        path = self.work / name
        path.write_text(text)
        return str(path)

    def test_input_preserves_zero_and_duplicate_charge_rows(self):
        path = self.write("input", "2 3\n0 0 0 H\n0 0 0.8 H\n4 0 0 0.1\n4 0 0 0.3\n5 0 0 0\n")
        with contextlib.redirect_stdout(io.StringIO()):
            atoms, charges, n_qm, n_pc = qm.parse_namd_input(path)
        self.assertEqual((n_qm, n_pc), (2, 3))
        self.assertEqual([a['element'] for a in atoms], ['h', 'h'])
        self.assertEqual([p['q'] for p in charges], [0.1, 0.3, 0.0])

    def test_truncated_input_is_rejected(self):
        path = self.write("input", "2 1\n0 0 0 H\n0 0 0.8 H\n")
        with self.assertRaises(RuntimeError):
            qm.parse_namd_input(path)

    def test_coord_units(self):
        path = self.work / 'coord'
        qm.write_turbomole_coord(path, [{'element':'h', 'x':0.529177210903, 'y':0.0, 'z':0.0}])
        self.assertAlmostEqual(float(path.read_text().splitlines()[1].split()[0]), 1.0)

    def test_gradient_sign_units_and_last_cycle(self):
        block = lambda e, g: f"cycle = 1 SCF energy = {e}\n0 0 0 h\n{g} 0.0D+00 0.0D+00\n"
        path = self.write('gradient', '$grad\n' + block('-2.0', '0.0D+00') + block('-1.25', '1.0D-03') + '$end\n')
        energy, forces = qm.parse_turbomole_gradient(path, 1)
        self.assertEqual(energy, -1.25)
        self.assertAlmostEqual(forces[0][0], -0.001 * 627.509469 / 0.529177210903)

    def test_incomplete_gradient_is_rejected(self):
        path = self.write('gradient', '$grad\ncycle = 1 SCF energy = -1.25\n0 0 0 h\n$end\n')
        with self.assertRaises((RuntimeError, ValueError)):
            qm.parse_turbomole_gradient(path, 1)

    def test_point_charge_force_expansion(self):
        charges = [{'x':x,'y':0.0,'z':0.0,'q':q} for x,q in [(4,.1),(4,.3),(5,0),(-4,-.2)]]
        compact, mapping = qm.prepare_turbomole_point_charges(charges)
        self.assertEqual(len(compact), 2)
        forces = qm.expand_point_charge_forces([[4.,8.,12.],[-2.,4.,0.]], mapping)
        for actual, expected in zip(forces, [[1.,2.,3.],[3.,6.,9.],[0.,0.,0.],[-2.,4.,0.]]):
            for a, b in zip(actual, expected): self.assertAlmostEqual(a,b)

    def test_cancelling_coincident_charges_are_rejected(self):
        charges = [{'x':0,'y':0,'z':0,'q':q} for q in (0.2,-0.2)]
        with self.assertRaises(RuntimeError): qm.prepare_turbomole_point_charges(charges)

    def test_point_charge_gradient_count_is_checked(self):
        path = self.write('pc_gradient', '$point_charge_gradients\n0 0 0\n$end\n')
        with self.assertRaises(RuntimeError): qm.parse_turbomole_pc_gradient(path, 2)

    def test_link_order_and_inverse_mapping(self):
        atoms = [{'element':e,'x':x,'y':0,'z':0} for e,x in [('c',0),('o',3),('h',1.09)]]
        order = qm.reorder_qm_atoms_by_pdb(atoms, 1)
        self.assertEqual(order, [0,2,1])
        self.assertEqual(qm.restore_original_order(['carbon','link','oxygen'], order), ['carbon','oxygen','link'])

    def test_invalid_permutation_is_rejected(self):
        with self.assertRaises(RuntimeError): qm.validate_order_permutation([0,0], 2)

    def test_mulliken_charges(self):
        path = self.write('scf', 'atom charge n(s)\n1h 0.125 0\n2h -0.125 0\n\n')
        self.assertEqual(qm.parse_turbomole_charges(path, 2), [0.125,-0.125])

    def test_missing_mulliken_output_is_fatal(self):
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            qm.parse_turbomole_charges(str(self.work/'absent'), 2)

    def test_partial_mulliken_output_is_fatal(self):
        path = self.write('scf', 'atom charge n(s)\n1h 0.1 0\n\n')
        with self.assertRaises(RuntimeError): qm.parse_turbomole_charges(path, 2)

    def test_result_contract(self):
        path = self.work/'result'
        qm.write_namd_result(path, -1., [[1.,2.,3.]], [.2], [[4.,5.,6.]])
        rows = [line.split() for line in path.read_text().splitlines()]
        self.assertEqual([len(r) for r in rows], [2,4,3])
        self.assertEqual(int(rows[0][1]), 1)

    def test_cli_with_synthetic_external_programs(self):
        run = self.work/'turbo-exec'/'0'; run.mkdir(parents=True)
        template = run.parent/'input_1'; template.mkdir()
        (template/'control').write_text('$title\nSynthetic protocol test\n$end\n')
        input_file = run/'qmmm_0.input'
        input_file.write_text('2 4\n0 0 0 H\n0 0 0.8 H\n4 0 0 0.1\n4 0 0 0.3\n5 0 0 0\n-4 0 0 -0.2\n')
        scf = self.work/'fake_scf'
        scf.write_text('#!/usr/bin/env python3\nprint("atom charge n(s)\\n1h 0.1 0\\n2h -0.1 0\\n")\n')
        grad = self.work/'fake_grad'
        grad.write_text('''#!/usr/bin/env python3
from pathlib import Path
coords = Path('coord').read_text().splitlines()[1:-1]
Path('gradient').write_text('$grad\\ncycle = 1 SCF energy = -1.25\\n' + '\\n'.join(coords) + '\\n1.0D-03 0 0\\n-1.0D-03 0 0\\n$end\\n')
Path('pc_gradient').write_text('$point_charge_gradients\\n1.0D-03 0 0\\n-2.0D-03 0 0\\n$end\\n')
''')
        scf.chmod(0o755); grad.chmod(0o755)
        env = {k:v for k,v in os.environ.items() if not k.startswith('QM_')}
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run([sys.executable,str(ROOT/'turbomole-namd.py'),'--coord-order','namd','--scf-cmd',str(scf),'--grad-cmd',str(grad),str(input_file)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        rows = [list(map(float,l.split())) for l in Path(str(input_file)+'.result').read_text().splitlines()]
        self.assertEqual(len(rows),7)
        self.assertEqual(rows[0][1],4)
        self.assertAlmostEqual(rows[0][0],-1.25*627.509469,places=8)
        self.assertAlmostEqual(rows[1][0],-.001*627.509469/.529177210903,places=8)
        self.assertEqual([r[3] for r in rows[1:3]],[.1,-.1])
        self.assertEqual(rows[5],[0.,0.,0.])
        self.assertEqual((run/'step').read_text(),'1')
        self.assertTrue((run.parent/'output_1/control').is_file())
        self.assertTrue((run.parent/'results_1/ridft0').is_file())

    def test_failed_scf_does_not_leave_a_previous_result(self):
        run = self.work/'turbo-exec'/'0'; run.mkdir(parents=True)
        input_file = run/'qmmm_0.input'
        input_file.write_text('1 1\n0 0 0 H\n4 0 0 0.1\n')
        previous = Path(str(input_file) + '.result')
        previous.write_text('previous evaluation\n')
        scf = self.work/'failed_scf'
        scf.write_text('#!/usr/bin/env python3\nraise SystemExit(7)\n')
        scf.chmod(0o755)
        env = {k:v for k,v in os.environ.items() if not k.startswith('QM_')}
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run([sys.executable, str(ROOT/'turbomole-namd.py'),
                                 '--coord-order', 'namd', '--scf-cmd', str(scf), str(input_file)],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exited with code 7', result.stderr)
        self.assertFalse(previous.exists())
        self.assertFalse((run/'step').exists())


if __name__ == '__main__': unittest.main()
