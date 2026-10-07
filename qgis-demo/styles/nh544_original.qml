<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling|Fields|Forms|MapTips|Rendering">
  <!--
    NH544 Original Route — hazard-coloured rule-based line symbology.
    Colours mirror the React/deck.gl demo exactly:
      SAFE     → cyan   #00F0FF  (hazard < 0.4)
      WARNING  → amber  #FFAA00  (0.4 ≤ hazard < 0.8)
      CRITICAL → red    #FF3366  (hazard ≥ 0.8)
      STAGE 5  → dim red (route flooded / severed)
  -->
  <renderer-v2 type="RuleRenderer" forceraster="0" symbollevels="0" enableorderby="0">
    <rules key="{00000000-0000-0000-0000-000000000001}">

      <!-- Stage 5: flooded/severed — show dimmed red -->
      <rule key="{00000001-0000-0000-0000-000000000001}"
            label="Stage 5 – Flooded (severed)"
            filter="&quot;scenario_stage&quot; = 5">
        <symbol type="line" name="" alpha="0.6" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleLine" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="line_color" type="QString" value="255,51,102,153"/>
              <Option name="line_width" type="QString" value="0.5"/>
              <Option name="line_width_unit" type="QString" value="Pixel"/>
              <Option name="line_style" type="QString" value="solid"/>
              <Option name="capstyle" type="QString" value="round"/>
              <Option name="joinstyle" type="QString" value="round"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <!-- CRITICAL segments (hazard ≥ 0.8) -->
      <rule key="{00000001-0000-0000-0000-000000000002}"
            label="CRITICAL  (≥ 0.8 m²/s)"
            filter="&quot;scenario_stage&quot; != 5 AND &quot;hazard_coefficient&quot; >= 0.8">
        <symbol type="line" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleLine" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="line_color" type="QString" value="255,51,102,255"/>
              <Option name="line_width" type="QString" value="4"/>
              <Option name="line_width_unit" type="QString" value="Pixel"/>
              <Option name="line_style" type="QString" value="solid"/>
              <Option name="capstyle" type="QString" value="round"/>
              <Option name="joinstyle" type="QString" value="round"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <!-- WARNING segments (0.4–0.8) -->
      <rule key="{00000001-0000-0000-0000-000000000003}"
            label="WARNING   (0.4 – 0.8 m²/s)"
            filter="&quot;scenario_stage&quot; != 5 AND &quot;hazard_coefficient&quot; >= 0.4 AND &quot;hazard_coefficient&quot; &lt; 0.8">
        <symbol type="line" name="" alpha="1" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleLine" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="line_color" type="QString" value="255,170,0,220"/>
              <Option name="line_width" type="QString" value="3"/>
              <Option name="line_width_unit" type="QString" value="Pixel"/>
              <Option name="line_style" type="QString" value="solid"/>
              <Option name="capstyle" type="QString" value="round"/>
              <Option name="joinstyle" type="QString" value="round"/>
            </Option>
          </layer>
        </symbol>
      </rule>

      <!-- SAFE segments (< 0.4) -->
      <rule key="{00000001-0000-0000-0000-000000000004}"
            label="SAFE      (&lt; 0.4 m²/s)"
            filter="ELSE">
        <symbol type="line" name="" alpha="0.9" clip_to_extent="1" force_rhr="0">
          <data_defined_properties/>
          <layer class="SimpleLine" enabled="1" locked="0" pass="0">
            <Option type="Map">
              <Option name="line_color" type="QString" value="0,240,255,200"/>
              <Option name="line_width" type="QString" value="2"/>
              <Option name="line_width_unit" type="QString" value="Pixel"/>
              <Option name="line_style" type="QString" value="solid"/>
              <Option name="capstyle" type="QString" value="round"/>
              <Option name="joinstyle" type="QString" value="round"/>
            </Option>
          </layer>
        </symbol>
      </rule>

    </rules>
  </renderer-v2>

  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="7" fontFamily="JetBrains Mono,monospace" textColor="200,200,200,255"
                  fontItalic="0" fontBold="0" textOpacity="1" namedStyle="Regular"
                  fieldName="concat(&quot;hazard_class&quot;, ' · ', format_number(&quot;hazard_coefficient&quot;,2), ' m²/s')"
                  isExpression="1">
        <text-buffer bufferColor="20,20,40,200" bufferOpacity="0.8" bufferSize="1"
                     bufferSizeUnits="MM" bufferDraw="1"/>
      </text-style>
      <placement placement="2" placementFlags="10" dist="0" distUnits="MM"
                 repeatDistance="300" repeatDistanceUnits="Pixel"
                 overrunDistance="0" overrunDistanceUnit="MM"/>
      <rendering displayAll="0" minFeatureSize="0" obstacle="1"
                 scaleVisibility="1" scaleMin="50000" scaleMax="1"/>
    </settings>
  </labeling>
</qgis>
