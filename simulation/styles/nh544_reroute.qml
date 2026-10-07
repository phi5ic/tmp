<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling|Fields|Forms|MapTips|Rendering">
  <!--
    PI-GNN Reroute Path — dashed green line, only visible at stage 5.
    Colour: #00FF9D (same as deck.gl demo)
  -->
  <renderer-v2 type="singleSymbol" forceraster="0" symbollevels="0" enableorderby="0">
    <symbols>
      <symbol type="line" name="0" alpha="0.9" clip_to_extent="1" force_rhr="0">
        <data_defined_properties/>
        <layer class="SimpleLine" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="line_color" type="QString" value="0,255,157,230"/>
            <Option name="line_width" type="QString" value="3"/>
            <Option name="line_width_unit" type="QString" value="Pixel"/>
            <Option name="line_style" type="QString" value="dash"/>
            <Option name="customdash" type="QString" value="6;3"/>
            <Option name="customdash_unit" type="QString" value="Pixel"/>
            <Option name="use_custom_dash" type="QString" value="1"/>
            <Option name="capstyle" type="QString" value="round"/>
            <Option name="joinstyle" type="QString" value="round"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>

  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="7" fontFamily="JetBrains Mono,monospace" textColor="0,255,157,255"
                  fontItalic="0" fontBold="1" textOpacity="1" namedStyle="Bold"
                  fieldName="'PI-GNN REROUTE · SAFE'"
                  isExpression="1">
        <text-buffer bufferColor="10,30,20,200" bufferOpacity="0.8" bufferSize="1"
                     bufferSizeUnits="MM" bufferDraw="1"/>
      </text-style>
      <placement placement="2" placementFlags="10" dist="0" distUnits="MM"
                 repeatDistance="500" repeatDistanceUnits="Pixel"/>
      <rendering displayAll="0" minFeatureSize="0" obstacle="1"
                 scaleVisibility="1" scaleMin="50000" scaleMax="1"/>
    </settings>
  </labeling>
</qgis>
