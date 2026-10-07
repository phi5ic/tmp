<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling|Fields|Forms|MapTips|Rendering">
  <!--
    Vehicle point track — rule-based:
      FMCG Truck   → green circle (connected) or white (VDTN)
      Fleeing Veh  → amber circle
    Sizes mirror deck.gl ScatterplotLayer radiusUnits:'pixels'.
  -->
  <renderer-v2 type="RuleRenderer" forceraster="0" symbollevels="0" enableorderby="0">
    <rules key="{00000000-0000-0000-0000-000000000010}">

      <!-- FMCG truck — VDTN offline mode (stage 3) -->
      <rule key="{00000002-0000-0000-0000-000000000001}"
            label="FMCG Truck (VDTN offline)"
            filter="&quot;vehicle_id&quot; = 'FMCG-Truck-01' AND &quot;network_mode&quot; = 'VDTN'">
        <symbol type="marker" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,255,255,255"/>
              <Option name="outline_color" type="QString" value="0,0,0,255"/>
              <Option name="outline_width" type="QString" value="1.5"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="12"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="circle"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <!-- FMCG truck — LTE/5G connected (all other stages) -->
      <rule key="{00000002-0000-0000-0000-000000000002}"
            label="FMCG Truck (LTE/5G)"
            filter="&quot;vehicle_id&quot; = 'FMCG-Truck-01' AND &quot;network_mode&quot; != 'VDTN'">
        <symbol type="marker" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="0,255,157,255"/>
              <Option name="outline_color" type="QString" value="0,0,0,255"/>
              <Option name="outline_width" type="QString" value="1.5"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="12"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="circle"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <!-- Fleeing vehicle — amber -->
      <rule key="{00000002-0000-0000-0000-000000000003}"
            label="Fleeing Vehicle (Civilian)"
            filter="&quot;vehicle_id&quot; = 'Fleeing-Vehicle-02'">
        <symbol type="marker" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="color" type="QString" value="255,170,0,255"/>
              <Option name="outline_color" type="QString" value="255,255,255,255"/>
              <Option name="outline_width" type="QString" value="1.5"/>
              <Option name="outline_width_unit" type="QString" value="Pixel"/>
              <Option name="size" type="QString" value="9"/>
              <Option name="size_unit" type="QString" value="Pixel"/>
              <Option name="name" type="QString" value="circle"/>
            </Option>
          </layer>
        </symbol>
      </rule>

    </rules>
  </renderer-v2>

  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="8" fontFamily="JetBrains Mono,monospace" textColor="240,244,248,255"
                  fontItalic="0" fontBold="0" textOpacity="1" namedStyle="Regular"
                  fieldName="concat(&quot;vehicle_id&quot;, '\n', &quot;network_mode&quot;)"
                  isExpression="1">
        <text-buffer bufferColor="10,15,30,220" bufferOpacity="0.9" bufferSize="1"
                     bufferSizeUnits="MM" bufferDraw="1"/>
      </text-style>
      <placement placement="1" xOffset="8" yOffset="-4" offsetUnits="Pixel"
                 quadOffset="4"/>
      <rendering displayAll="0" obstacle="1"
                 scaleVisibility="1" scaleMin="100000" scaleMax="1"/>
    </settings>
  </labeling>
</qgis>
