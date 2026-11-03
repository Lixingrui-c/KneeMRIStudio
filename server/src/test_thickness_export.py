import sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/"morphometry"))
from thickness_export import attach_thickness,export_thickness_surfaces
class Tests(unittest.TestCase):
 def item(self):
  v=np.array([[1,1,1],[2,1,1],[1,2,1],[2,2,1],[1,1,2]],float)
  f=np.array([[0,1,2],[1,2,3],[0,1,4]])
  item=dict(vertices_sub=v,faces=f,coverage_class=np.array([1,2,0],np.uint8))
  mesh=SimpleNamespace(vertices_sub=v,faces=f[:2])
  return item,mesh
 def test_values(self):
  item,m=self.item()
  attach_thickness(item,[(m,np.array([1,2,3,4,5]),np.ones(5,bool))])
  np.testing.assert_equal(item["thickness_mm"],[2,0,-1])
  np.testing.assert_equal(item["thickness_valid"],[1,1,0])
 def test_unmatched_not_zero(self):
  item,m=self.item()
  attach_thickness(item,[(m,np.ones(5),np.array([False,True,True,True,True]))])
  self.assertEqual(item["thickness_mm"][0],-1)
  self.assertEqual(item["thickness_valid"][0],0)
 def test_conflict(self):
  item,m=self.item()
  with self.assertRaises(ValueError):
   attach_thickness(item,[(m,np.ones(5),np.ones(5,bool)),(m,np.ones(5)*2,np.ones(5,bool))])
 def test_vtp(self):
  import xml.etree.ElementTree as ET
  item,m=self.item()
  attach_thickness(item,[(m,np.array([1,2,3,4,5]),np.ones(5,bool))])
  a=np.diag([.7,.4,.4,1]);a[:3,3]=[10,20,30]
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
   manifest=export_thickness_surfaces(d,dict(femur=item,tibia=item),a,"right")
   self.assertEqual(manifest["shared_data_range_mm"],[0,2])
   root=ET.parse(Path(d)/"femur_thickness.vtp")
   self.assertEqual(root.find('.//CellData/DataArray[@Name="thickness_mm"]').text,"2 0 -1")
   coords=np.fromstring(root.find('.//Points/DataArray').text,sep=" ").reshape(-1,3)
   np.testing.assert_allclose(coords[0],[10,20,30])
   try:
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
   except ImportError: return
   reader=vtkXMLPolyDataReader();reader.SetFileName(str(Path(d)/"femur_thickness.vtp"));reader.Update()
   self.assertEqual(reader.GetOutput().GetNumberOfCells(),3)
   self.assertEqual(reader.GetOutput().GetCellData().GetArray("thickness_mm").GetValue(0),2)
if __name__=="__main__": unittest.main()


