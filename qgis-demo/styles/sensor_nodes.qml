<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling|Fields|Forms|MapTips|Rendering">
  <!--
    Sensor node points — rule-based by hazard_class.
    SAFE     → cyan   diamond
    WARNING  → amber  diamond
    CRITICAL → red    diamond with halo
  -->
  <renderer-v2 type="RuleRenderer" forceraster="0" symbollevels="0" enableorderby="0">
    <rules key="{00000000-0000-0000-0000-000000000020}">

      <rule key="{00000003-0000-0000-0000-000000000001}"
            label="Sensor — CRITICAL"
            filter="&quot;hazard_class&quot; = 'CRITICAL'">
        <symbol type="marker" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,51,102,255"/>
              <Option name="outline_color" type="QString" value="255,200,200,255"/>
              <Option name="outline_width" type="QString" value="2"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="16"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="diamond"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <rule key="{00000003-0000-0000-0000-000000000002}"
            label="Sensor — WARNING"
            filter="&quot;hazard_class&quot; = 'WARNING'">
        <symbol type="marker" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,170,0,255"/>
              <Option name="outline_color" type="QString" value="255,255,255,200"/>
              <Option name="outline_width" type="QString" value="1.5"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="14"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="diamond"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <rule key="{00000003-0000-0000-0000-000000000003}"
            label="Sensor — SAFE / Monitoring"
            filter="ELSE">
        <symbol type="marker" name="" alpha="0.9" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="0,240,255,200"/>
              <Option name="outline_color" type="QString" value="255,255,255,150"/>
              <Option name="outline_width" type="QString" value="1"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="12"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="diamond"/>
            </Option>
          </layer>
        </symbol>
      </rule>

    </rules>
  </renderer-v2>

  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="8" fontFamily="JetBrains Mono,monospace" textColor="240,244,248,255"
                  fontItalic="0" fontBold="1" textOpacity="1" namedStyle="Bold"
                  fieldName="concat(&quot;sensor_id&quot;, '\n', &quot;hazard_class&quot;, ' · ', format_number(&quot;hazard_coefficient&quot;,2), ' m²/s')"
                  isExpression="1">
        <text-buffer bufferColor="10,15,30,220" bufferOpacity="0.9" bufferSize="1.2"
                     bufferSizeUnits="MM" bufferDraw="1"/>
      </text-style>
      <placement placement="1" xOffset="10" yOffset="-4" offsetUnits="Pixel"
                 quadOffset="4"/>
      <rendering displayAll="1" obstacle="0"/>
    </settings>
  </labeling>
</qgis>
