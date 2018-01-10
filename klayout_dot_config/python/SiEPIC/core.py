#################################################################################
#                SiEPIC Tools - core                                            #
#################################################################################

'''
Classes
 - Net: connectivity between pins. Used for netlist generation and verification
    data generated by class extensions cell.identify_nets()
 - Component: contains information about a layout component (cell with pins)
    data generated by class extensions cell.find_components()
    and will contain pin objects
 - Pin: pin details (direction); 
    data generated by class extensions cell.find_pins()

Netlist format
 <component>_<idx> Net1 Net2 ...

Data structure for netlist, and pointers.
 Component -> Pin -> Net
 - Find components, each one finds its pins
 - overlapping pins define nets
 (note that Python variables are actually pointers
 http://scottlobdell.me/2013/08/understanding-python-variables-as-pointers/
 so when we create an object which references another object, we can easily go backwards if need be)

Also functions:

 - WaveguideGUI
 - CalibreGUI
 - MonteCarloGUI
 
'''


import pya

'''
Net:
 - connection between pins
  - optical nets can only have two pins
  - electrical nets can have multiple pins
 - the pin variables point to Pin indexes
'''
class Net:
  def __init__(self, idx=None, _type=None, pins=None):
    self.idx = idx           # net number, index, should be unique, 0, 1, 2, ...
    self.type = _type        # one of PIN_TYPES, defined in SiEPIC._globals.PINTYPES 
    # for backwards linking (optional)
    self.pins = pins         # pin array, Pin[]    

  def display(self):
    print ('- net: %s, pins: %s' % (self.idx, [[p.pin_name, p.center.to_s(), p.component.component, p.component.component] for p in self.pins ]))
    
'''
Pin:
This is a class that describes pins on components and waveguides.
A pin consists of:
 - optical pin: a Path with 2 points, with it's vector giving the direction
 - electrical pin: a Box
 - a Text label giving it's name
 - a type: OPTICAL, I/O, ELECTRICAL
A pin can associated with:
 - a component
 - a net

Uses:
 - Waveguide snapping to nearest pin (in waveguide_from_path, and path.snap)
    - does not need info about component, net...
 - Component snapping to nearest pin (in snap_component)
    - does not need info about component, net...
 - Netlist extraction
    - needs connectivity: which component & net the pin belongs to
    
Pin defs:
 - transform: to move the pin
 - display: list the pin

'''
class Pin():
  def __init__(self, path=None, _type=None, box=None, polygon=None, component=None, net=None, pin_name=None ):
    from .utils import angle_vector
    from . import _globals
    self.path = path            # the pin's Path (Optical)
    if path:
      pts = path.get_points()
      self.center = (pts[0]+pts[1])*0.5  # center of the pin: a Point
      self.rotation = angle_vector(pts[1]-pts[0]) # direction / angle of the optical pin
    else:
      self.rotation = 0
    self.box = box              # the pin's Box (Electrical)
    if box:
      self.center = box.center()# center of the pin: a Point
    if polygon:
      self.center = polygon.center()# center of the pin: a Point
    self.type = _type           # one of PIN_TYPES, defined in SiEPIC._globals.PINTYPES 
    if net:                     # Net for netlist generation
      self.net = net            # which net this pin is connected to
    else:
      self.net = _globals.NET_DISCONNECTED
    self.pin_name = pin_name    # label read from the cell layout (PinRec text)
    self.component = component  # which component index this pin belongs to
    
  def transform(self, trans):
    # Transformation of the pin location
    from .utils import angle_vector
    if self.path:
      self.path = self.path.transformed(trans)
      pts = self.path.get_points()
      self.center = (pts[0]+pts[1])*0.5
      self.rotation = angle_vector(pts[0]-pts[1])
    return self

  def display(self):
    o = self
    print("- pin #%s: component_idx %s, pin_name %s, pin_type %s, net: %s, (%s), path: %s" %\
      (o.idx, o.component_idx, o.pin_name, o.type, o.net.idx, o.center, o.path) )

def display_pins(pins):
  print("Pins:")
  for o in pins:
    o.display()


'''
Component:
This is a class that describes components (PCells and fixed)
A component consists of:
 - a layout representation
 - additional information 

Uses:
 - Netlist extraction
    - needs connectivity: components and how they are connected (net)
    
Component defs:
 - display: list the component
 - transform: to move the component
 - find_pins
 
'''
class Component():
  def __init__(self, idx=None, component=None, instance=None, trans=None, library=None, params=None, pins=[], epins=[], nets=[], polygon=None, cell=None, basic_name=None ):
    self.idx = idx             # component index, should be unique, 0, 1, 2, ...
    self.component = component # which component (name) this pin belongs to
    self.instance = instance   # which component (instance) this pin belongs to
    self.trans = trans         # instance's location (.disp.x, y), mirror (.is_mirror), rotation (angle); in a ICplxTrans class http://www.klayout.de/doc-qt4/code/class_ICplxTrans.html
    self.library = library     # compact model library
    self.pins = pins           # an array of all the optical pins, Pin[]
    self.npins = len(pins)     # number of pins
    self.params = params       # Spice parameters
    self.polygon = polygon     # The component's DevRec polygon/box outline
    self.center = polygon.bbox().center()  # Point
    self.cell = cell           # component's cell
    self.basic_name = basic_name # component's basic_name (especially for PCells)
    from .utils import get_technology
    TECHNOLOGY = get_technology()
    self.Dcenter = self.center.to_dtype(TECHNOLOGY['dbu'])
  def display(self):
    from . import _globals
    c = self
    text = ("- component: %s-%s / %s, (%s), (%s), npins %s, opt pins %s, elec pins %s, IO pins %s, has compact model: %s" %\
      ( c.component, c.idx, c.instance, c.trans, c.Dcenter, c.npins, \
      [[p.pin_name, p.center.to_s(), p.net.idx] for p in c.pins if p.type == _globals.PIN_TYPES.OPTICAL], \
      [[p.pin_name, p.center.to_s(), p.net.idx] for p in c.pins if p.type == _globals.PIN_TYPES.ELECTRICAL], \
      [[p.pin_name, p.center.to_s(), p.net.idx] for p in c.pins if p.type == _globals.PIN_TYPES.OPTICALIO], \
      c.has_model() ) )
    print(text)
    return text

  def find_pins(self):        
    return self.cell.find_pins_component(self)

  def has_model(self):
 
    # check if this component has a compact model in the INTC library
    from .utils import get_technology, get_technology_by_name
    TECHNOLOGY = get_technology()
    TECHNOLOGY = get_technology_by_name(TECHNOLOGY['technology_name'])

    from ._globals import INTC_ELEMENTS
    return ("design kits::"+TECHNOLOGY['technology_name'].lower()+"::"+self.component.lower()) in INTC_ELEMENTS
  
  def get_polygons(self):
    from utils import get_layout_variables
    TECHNOLOGY, lv, ly, cell = get_layout_variables()  

    r = pya.Region()

    s = self.cell.begin_shapes_rec(ly.layer(TECHNOLOGY['Waveguide']))
    while not(s.at_end()):
      if s.shape().is_polygon() or s.shape().is_box() or s.shape().is_path():
        r.insert ( s.shape().polygon.transformed(s.itrans()) )
      s.next()

    s = self.cell.begin_shapes_rec(ly.layer(TECHNOLOGY['PinRec']))
    import math
    from .utils import angle_vector
    while not(s.at_end()):
      if s.shape().is_path():
        p = s.shape().path.transformed(s.itrans())
        # extend the pin path by 1 micron for FDTD simulations
        pts = [pt for pt in p.each_point()]
        rotation = angle_vector(pts[0]-pts[1])*math.pi/180 # direction / angle of the optical pin
        pts[1] = (pts[1]-pya.Point(int(math.cos(rotation)*1000),int(math.sin(rotation)*1000) )).to_p()
        r.insert ( pya.Path(pts, p.width).polygon() )
      s.next()

    r.merge()
    polygons = [p for p in r.each_merged()]
    
    return polygons

class WaveguideGUI():

  def __init__(self):
    import os
  
    ui_file = pya.QFile(os.path.join(os.path.dirname(os.path.realpath(__file__)), "files", "waveguide_gui.ui"))
    ui_file.open(pya.QIODevice().ReadOnly)
    self.window = pya.QFormBuilder().load(ui_file, pya.Application.instance().main_window())
    ui_file.close
    
    table = self.window.findChild('layerTable')
    table.setColumnCount(3)
    table.setHorizontalHeaderLabels([ "Layer","Width","Offset"])
    table.setColumnWidth(0, 140)
    table.setColumnWidth(1, 50)
    table.setColumnWidth(2, 50)

    #Button Bindings
    self.window.findChild('ok').clicked(self.ok)
    self.window.findChild('cancel').clicked(self.close)
    self.window.findChild('numLayers').valueChanged(self.updateTable)
    self.window.findChild('radioStrip').toggled(self.updateFields)
    self.window.findChild('radioRib').toggled(self.updateFields)
    self.window.findChild('radioSlot').toggled(self.updateFields)
    self.window.findChild('radioCustom').toggled(self.updateFields)
    self.window.findChild('adiabatic').toggled(self.updateFields)
    self.window.findChild('radioStrip').click()
    self.initialized = False
    self.layers = []
    
  def updateTable(self, val):
    table = self.window.findChild("layerTable")
    cur = table.rowCount
    if cur > val:
      for i in range(val, cur):
        table.removeRow(i)
    else:
      for i in range(cur, val):
        table.insertRow(i)
        item = pya.QComboBox(table)
        item.clear()
        item.addItems(self.layers)
        table.setCellWidget(i, 0, item)
        item = pya.QLineEdit(table)
        item.setText("0.5")
        table.setCellWidget(i, 1, item)
        item = pya.QLineEdit(table)
        item.setText("0")
        table.setCellWidget(i, 2, item)
        
  def updateFields(self, val):
  
    if self.window.findChild('radioStrip').isChecked():
      self.window.findChild('stripWidth').setEnabled(True)
      self.window.findChild('stripLayer').setEnabled(True)
    else:
      self.window.findChild('stripWidth').setEnabled(False)
      self.window.findChild('stripLayer').setEnabled(False)
      
    if self.window.findChild('radioRib').isChecked():
      self.window.findChild('ribWidth1').setEnabled(True)
      self.window.findChild('ribWidth2').setEnabled(True)
      self.window.findChild('ribLayer1').setEnabled(True)
      self.window.findChild('ribLayer2').setEnabled(True)
    else:
      self.window.findChild('ribWidth1').setEnabled(False)
      self.window.findChild('ribWidth2').setEnabled(False)
      self.window.findChild('ribLayer1').setEnabled(False)
      self.window.findChild('ribLayer2').setEnabled(False)
      
    if self.window.findChild('radioSlot').isChecked():
      self.window.findChild('slotWidth1').setEnabled(True)
      self.window.findChild('slotWidth2').setEnabled(True)
      self.window.findChild('slotLayer').setEnabled(True)
    else:
      self.window.findChild('slotWidth1').setEnabled(False)
      self.window.findChild('slotWidth2').setEnabled(False)
      self.window.findChild('slotLayer').setEnabled(False)
      
    if self.window.findChild('radioCustom').isChecked():
      self.window.findChild('numLayers').setEnabled(True)
      self.window.findChild('layerTable').setEnabled(True)
    else:
      self.window.findChild('numLayers').setEnabled(False)
      self.window.findChild('layerTable').setEnabled(False)
      
    if self.window.findChild('adiabatic').isChecked():
      self.window.findChild('bezier').setEnabled(True)
    else:
      self.window.findChild('bezier').setEnabled(False)

  def updateLayers(self, val):
    self.window.findChild("stripLayer").clear()
    self.window.findChild("ribLayer1").clear()
    self.window.findChild("ribLayer2").clear()
    self.window.findChild("slotLayer").clear()
    self.layers = []
    lv = pya.Application.instance().main_window().current_view()
    if lv == None:
      raise Exception("No view selected")

    itr = lv.begin_layers()
    while True:
      if itr == lv.end_layers():
        break
      else:
        self.layers.append(itr.current().name + " - " + itr.current().source.split('@')[0])
        itr.next()
    self.window.findChild("stripLayer").addItems(self.layers)
    self.window.findChild("ribLayer1").addItems(self.layers)
    self.window.findChild("ribLayer2").addItems(self.layers)
    self.window.findChild("slotLayer").addItems(self.layers)
    
    self.window.findChild("ribLayer2").setCurrentIndex(2)

  def show(self):
    self.updateLayers(0)
    self.updateTable(0)
    self.initialized = True
    self.window.show()
  
  def close(self, val):
    self.window.close()

  def ok(self, val):
    self.window.close()
    from . import scripts
    scripts.waveguide_from_path()
  
  def get_parameters(self):
    if not self.initialized:
      self.show()
      return None
    params = { 'radius': float(self.window.findChild('radius').text),
               'width': 0,
               'adiabatic': self.window.findChild('adiabatic').isChecked(),
               'bezier': float(self.window.findChild('bezier').text),
               'wgs':[] }

    if self.window.findChild('radioStrip').isChecked():
    
      layer = self.window.findChild('stripLayer').currentText
      params['wgs'].append({'layer': layer.split(' - ')[0], 'width': float(self.window.findChild('stripWidth').text), 'offset': 0})
      params['width'] = params['wgs'][0]['width']
      
    elif self.window.findChild('radioRib').isChecked():
      layer = self.window.findChild('ribLayer1').currentText
      params['wgs'].append({'layer': layer.split(' - ')[0], 'width': float(self.window.findChild('ribWidth1').text), 'offset': 0})
      layer = self.window.findChild('ribLayer2').currentText
      params['wgs'].append({'layer': layer.split(' - ')[0], 'width': float(self.window.findChild('ribWidth2').text), 'offset': 0})
      params['width'] = params['wgs'][0]['width']
      
    elif self.window.findChild('radioSlot').isChecked():
      w1 = float(self.window.findChild('slotWidth1').text)
      w2 = float(self.window.findChild('slotWidth2').text)
      layer = self.window.findChild('slotLayer').currentText
      params['wgs'].append({'layer': layer.split(' - ')[0], 'width': (w1-w2)/2,'offset': (w1+w2)/4})
      params['wgs'].append({'layer': layer.split(' - ')[0], 'width': (w1-w2)/2,'offset': -(w1+w2)/4})
      params['width'] = w1
    elif self.window.findChild('radioCustom').isChecked():
      table = self.window.findChild('layerTable')
      for i in range(0, int(self.window.findChild('numLayers').value)):
        layer = table.cellWidget(i,0).currentText
        params['wgs'].append({'layer': layer.split(' - ')[0], 'width': float(table.cellWidget(i,1).text), 'offset': float(table.cellWidget(i,2).text)})
        w = (params['wgs'][-1]['width']/2+params['wgs'][-1]['offset'])*2
        if params['width'] < w:
          params['width'] = w
    return params

class CalibreGUI():
  def __init__(self):
    import os
  
    ui_file = pya.QFile(os.path.join(os.path.dirname(os.path.realpath(__file__)), "files", "calibre_drc_gui.ui"))
    ui_file.open(pya.QIODevice().ReadOnly)
    self.window = pya.QFormBuilder().load(ui_file, pya.Application.instance().main_window())
    ui_file.close
    
    #Button Bindings
    self.window.findChild('connect').clicked(self.ok)
    self.window.findChild('cancel').clicked(self.close)
    self.status = None
    
  def show(self):
    self.window.show()
  
  def close(self, val):
    self.status = False
    self.window.close()
    from . import scripts
    scripts.calibreDRC()

  def ok(self, val):
    self.status = True
    self.window.close()
    from . import scripts
    scripts.calibreDRC()
    
  def return_status(self):
    status = self.status
    self.status = None
    return status
  
  def get_parameters(self):
    return {'url': self.window.findChild('url').text,
            'port': self.window.findChild('port').text,
            'pdk': self.window.findChild('pdk').text,
            'calibre': self.window.findChild('calibre').text,
            'identity': self.window.findChild('identity').text}

class MonteCarloGUI():

  def __init__(self):
    import os
  
    ui_file = pya.QFile(os.path.join(os.path.dirname(os.path.realpath(__file__)), "files", "monte_carlo_gui.ui"))
    ui_file.open(pya.QIODevice().ReadOnly)
    self.window = pya.QFormBuilder().load(ui_file, pya.Application.instance().main_window())
    ui_file.close
    
    self.window.findChild('run').clicked(self.ok)
    self.window.findChild('cancel').clicked(self.close)
    self.status = None
    
  def show(self):
    self.window.show()
  
  def close(self, val):
    self.status = False
    self.window.close()
    from . import lumerical
    lumerical.interconnect.monte_carlo()

  def ok(self, val):
    self.status = True
    self.window.close()
    from .lumerical import interconnect
    interconnect.monte_carlo()
    
  def return_status(self):
    status = self.status
    self.status = None
    return status

  def get_parameters(self):
    return {}