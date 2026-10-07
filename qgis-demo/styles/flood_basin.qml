<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling|Fields|Forms|MapTips|Rendering">
  <!--
    Chalakudy Flood Basin polygon — semi-transparent red fill, bright red outline.
    Mirrors deck.gl PolygonLayer: fill rgba(255,51,102,100), stroke rgba(255,51,102,255)
  -->
  <renderer-v2 type="singleSymbol" forceraster="0" symbollevels="0" enableorderby="0">
    <symbols>
      <symbol type="fill" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <data_defined_properties/>
        <layer class="SimpleFill" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="color" type="QString" value="255,51,102,100"/>
            <Option name="outline_color" type="QString" value="255,51,102,255"/>
            <Option name="outline_width" type="QString" value="2"/>
            <Option name="outline_width_unit" type="QString" value="Pixel"/>
            <Option name="outline_style" type="QString" value="solid"/>
            <Option name="style" type="QString" value="solid"/>
            <Option name="joinstyle" type="QString" value="miter"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>

  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="9" fontFamily="JetBrains Mono,monospace" textColor="255,51,102,255"
                  fontItalic="0" fontBold="1" textOpacity="1" namedStyle="Bold"
                  fieldName="'⚠ CHALAKUDY FLOOD BASIN'"
                  isExpression="1">
        <text-buffer bufferColor="20,10,15,200" bufferOpacity="0.85" bufferSize="1.5"
                     bufferSizeUnits="MM" bufferDraw="1"/>
      </text-style>
      <placement placement="4" centroidWhole="0"/>
      <rendering displayAll="1" obstacle="0"/>
    </settings>
  </labeling>
</qgis>
